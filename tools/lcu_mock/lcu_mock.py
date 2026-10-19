"""A fake League client (docs/architecture.md, section 5): `just lcu-mock <session>`.

    lcu_mock.py <session.json> [--dir runs/lcu-mock] [--port 0] [--latency-ms 0]

Writes `lockfile` (the client's format) and `root.pem` into `--dir`, then serves HTTPS on
127.0.0.1 with a certificate chained to that root, like the real client. Requests need the
lockfile's password (Basic auth, user `riot`). The session file's steps are replayed one at a
time: `POST /mock/step` moves to the next, `GET /mock/state` says where it is. Every write the
app makes (PUT, POST, PATCH, DELETE outside `/mock/`) is recorded and listed by
`GET /mock/recorded`, so tests can check what was imported.

The account side the imports touch is kept in memory, with made-up defaults, never in session
files: rune pages (two of the player's, room for one more), the page inventory, the current
summoner, item sets (one of the player's), and the spell selection, which is laid over the
local player in the session. The client's game data (rune, spell and item names and icon
paths) comes from `game_data.json` next to this file, the same for every session; champions
get the client's `squarePortraitPath`. Every icon path in the game data serves a generated
placeholder PNG, a square in a colour taken from the path, so no Riot artwork is needed.

The client's websocket is there too: a `[5, "<topic>"]` message subscribes, and every step the
replay moves to sends the subscribers of the champion-select session topic
`[8, "<topic>", {"data", "eventType", "uri"}]`, as the client does.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import ipaddress
import json
import os
import secrets
import ssl
import struct
import sys
import threading
import time
import zlib
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast, override

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

SESSION = "/lol-champ-select/v1/session"
CHAMPIONS = "/lol-game-data/assets/v1/champion-summary.json"
PAGES = "/lol-perks/v1/pages"
INVENTORY = "/lol-perks/v1/inventory"
SUMMONER = "/lol-summoner/v1/current-summoner"
SELECTION = "/lol-champ-select/v1/session/my-selection"
SUMMONER_ID = 1
SESSION_EVENT = "OnJsonApiEvent_lol-champ-select_v1_session"
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
GAME_DATA = Path(__file__).with_name("game_data.json")


def game_data() -> dict[str, object]:
    """The game data documents by path (`/lol-game-data/assets/v1/...`)."""
    data: dict[str, object] = json.loads(GAME_DATA.read_text(encoding="utf-8"))
    return {path: doc for path, doc in data.items() if path.startswith("/")}


def with_portraits(champions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The champion summary with the icon path the client gives each champion."""
    path = "/lol-game-data/assets/v1/champion-icons/{}.png"
    return [{"squarePortraitPath": path.format(c.get("id")), **c} for c in champions]


def icon_paths(documents: dict[str, object]) -> set[str]:
    """Every `iconPath` and `squarePortraitPath` in the game data documents."""
    paths: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in cast(dict[str, object], node).items():
                if key in ("iconPath", "squarePortraitPath") and isinstance(value, str):
                    paths.add(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in cast(list[object], node):
                walk(value)

    walk(documents)
    return paths


def placeholder_png(path: str, size: int = 32) -> bytes:
    """A square PNG in a colour derived from `path`, with a lighter border."""
    r, g, b = hashlib.sha256(path.encode()).digest()[:3]
    fill = bytes((r // 2 + 64, g // 2 + 64, b // 2 + 64))
    edge = bytes((min(255, fill[0] + 60), min(255, fill[1] + 60), min(255, fill[2] + 60)))
    rows = b"".join(
        b"\0"
        + b"".join(edge if min(x, y, size - 1 - x, size - 1 - y) < 2 else fill for x in range(size))
        for y in range(size)
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


class Subscriber:
    """One websocket connection and the topics it subscribed to; writes are serialised."""

    def __init__(self, wfile: Any) -> None:
        self.wfile = wfile
        self.topics: set[str] = set()
        self.lock = threading.Lock()

    def send(self, payload: object, opcode: int = 0x1) -> None:
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        header = bytes([0x80 | opcode])
        if len(data) < 126:
            header += bytes([len(data)])
        elif len(data) < 1 << 16:
            header += bytes([126]) + len(data).to_bytes(2, "big")
        else:
            header += bytes([127]) + len(data).to_bytes(8, "big")
        with self.lock:
            try:
                self.wfile.write(header + data)
                self.wfile.flush()
            except OSError:
                pass  # the app went away; its reader ends the connection


def read_frame(rfile: Any) -> tuple[int, bytes] | None:
    """(opcode, payload) of the next client frame, unmasked; `None` at end of stream."""
    head = rfile.read(2)
    if len(head) < 2:
        return None
    opcode, length = head[0] & 0x0F, head[1] & 0x7F
    if length == 126:
        length = int.from_bytes(rfile.read(2), "big")
    elif length == 127:
        length = int.from_bytes(rfile.read(8), "big")
    mask = rfile.read(4) if head[1] & 0x80 else b"\0\0\0\0"
    payload = rfile.read(length)
    return opcode, bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


ITEM_SETS = f"/lol-item-sets/v1/item-sets/{SUMMONER_ID}/sets"


def default_pages() -> list[dict[str, Any]]:
    """The player's own pages: one editable, one preset."""
    perks = [8010, 9111, 9104, 8014, 8304, 8347, 5005, 5008, 5001]
    mine = {"id": 101, "name": "My Lee Sin", "isEditable": True, "primaryStyleId": 8000,
            "subStyleId": 8300, "selectedPerkIds": perks}  # fmt: skip
    return [mine, {"id": 102, "name": "Domination preset", "isEditable": False}]


class Raw(str):
    """JSON text served and stored exactly as given, never decoded and re-encoded."""


THEIR_SET = (
    '{"title": "My Lee Sin", "blocks":[ ],"x-future": {"n": 2.50, "s": "\\u00e9", "list": [1,  2]},'
    ' "associatedChampions": [64]}'
)
"""The player's own item set: odd spacing, an escape, `2.50`, and a field nobody knows yet."""


def default_item_sets() -> Raw:
    return Raw(f'{{"accountId":1,"itemSets":[{THEIR_SET}],"timestamp":0}}')


@dataclass
class Replay:
    """The session file and how far it has been played."""

    steps: list[dict[str, Any]]
    champions: list[dict[str, Any]]
    step: int = 0
    recorded: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    lock: threading.Lock = field(default_factory=threading.Lock)
    pages: list[dict[str, Any]] = field(default_factory=default_pages)
    page_capacity: int = 3
    item_sets: Raw = field(default_factory=default_item_sets)
    """The item set document, as raw text."""
    item_sets_fail: bool = False
    """Answer reads of the item sets with HTTP 500."""
    spells: tuple[int, int] | None = None
    """The spell selection, D then F, laid over the local player; `None` keeps the session's."""
    subscribers: list[Subscriber] = field(default_factory=list[Subscriber])
    game_data: dict[str, object] = field(default_factory=game_data)

    @classmethod
    def load(cls, path: Path) -> Replay:
        data: dict[str, Any] = json.loads(path.read_text())
        steps: list[dict[str, Any]] = data["steps"]
        if not steps:
            raise ValueError(f"{path}: `steps` must be a non-empty list")
        champions: list[dict[str, Any]] = data.get("champions", [])
        return cls(steps=steps, champions=with_portraits(champions))

    def icons(self) -> set[str]:
        """The icon paths the client would serve: the game data's and the champions'."""
        with self.lock:
            return icon_paths({**self.game_data, CHAMPIONS: self.champions})

    def current(self) -> dict[str, Any]:
        with self.lock:
            return self.steps[self.step]

    def session(self) -> dict[str, Any] | None:
        """The current step's session with the spell selection on the local player."""
        with self.lock:
            session: dict[str, Any] | None = self.steps[self.step].get("session")
            if session is None or self.spells is None:
                return session
            local = session.get("localPlayerCellId")
            d, f = self.spells
            team = [
                {**m, "spell1Id": d, "spell2Id": f} if m.get("cellId") == local else m
                for m in session.get("myTeam", [])
            ]
            return {**session, "myTeam": team}

    def advance(self) -> dict[str, Any]:
        return self.set_step(self.step + 1)

    def set_step(self, step: int) -> dict[str, Any]:
        """Moves to `step` (kept in range) and tells websocket subscribers, like the client."""
        with self.lock:
            self.step = max(0, min(step, len(self.steps) - 1))
            moved = {"step": self.step, "name": self.steps[self.step].get("name")}
            subscribers = [s for s in self.subscribers if SESSION_EVENT in s.topics]
        session = self.session()
        event = {
            "data": session,
            "eventType": "Delete" if session is None else "Update",
            "uri": SESSION,
        }
        for subscriber in subscribers:
            subscriber.send([8, SESSION_EVENT, event])
        return moved


def make_handler(replay: Replay, password: str, latency: float) -> type[BaseHTTPRequestHandler]:
    expected = "Basic " + base64.b64encode(f"riot:{password}".encode()).decode()

    class Handler(BaseHTTPRequestHandler):
        @override
        def log_message(self, format: str, *args: object) -> None:
            pass  # quiet: tests read /mock/recorded instead

        def _send_image(self, data: bytes) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send(self, status: HTTPStatus, body: object | None = None) -> None:
            if body is None:
                data = b""
            elif isinstance(body, Raw):
                data = body.encode()
            else:
                data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorised(self) -> bool:
            if self.headers.get("Authorization") == expected:
                return True
            self._send(HTTPStatus.UNAUTHORIZED, {"message": "bad credentials"})
            return False

        def _body(self) -> tuple[object, str]:
            """The request body, parsed (or as text when it isn't JSON), and as raw text."""
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode(errors="replace") if length else ""
            try:
                return (json.loads(raw) if raw else None), raw
            except json.JSONDecodeError:
                return raw, raw

        def do_GET(self) -> None:
            if not self._authorised():
                return
            if self.headers.get("Upgrade", "").lower() == "websocket":
                self._websocket()
                return
            time.sleep(latency)
            if self.path in replay.icons():
                self._send_image(placeholder_png(self.path))
                return
            self._send(*self._read())

        def _read(self) -> tuple[HTTPStatus, object]:
            """The client's answer to a GET of `self.path`."""
            with replay.lock:
                step = replay.steps[replay.step]
                answers: dict[str, object] = {
                    "/mock/state": {"step": replay.step, "name": step.get("name")},
                    "/mock/recorded": list(replay.recorded),
                    CHAMPIONS: replay.champions,
                    PAGES: list(replay.pages),
                    INVENTORY: {"ownedPageCount": replay.page_capacity},
                    SUMMONER: {"summonerId": SUMMONER_ID},
                    ITEM_SETS: replay.item_sets,
                    **replay.game_data,
                }
            if self.path == ITEM_SETS and replay.item_sets_fail:
                return HTTPStatus.INTERNAL_SERVER_ERROR, {"message": "item sets unavailable"}
            if self.path == SESSION:
                session = replay.session()
                if session is None:  # what the client answers outside champion select
                    return HTTPStatus.NOT_FOUND, {"message": "No active delegate"}
                return HTTPStatus.OK, session
            if self.path in answers:
                return HTTPStatus.OK, answers[self.path]
            return HTTPStatus.NOT_FOUND, {"message": f"not mocked: {self.path}"}

        def _websocket(self) -> None:
            """Upgrades to a websocket and serves subscriptions until the app closes it."""
            key = self.headers.get("Sec-WebSocket-Key", "")
            accept = base64.b64encode(hashlib.sha1((key + WEBSOCKET_GUID).encode()).digest())  # noqa: S324 (RFC 6455)
            self.wfile.write(
                b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                b"Sec-WebSocket-Accept: " + accept + b"\r\n\r\n"
            )
            self.wfile.flush()
            self.close_connection = True
            subscriber = Subscriber(self.wfile)
            with replay.lock:
                replay.subscribers.append(subscriber)
            try:
                while (frame := read_frame(self.rfile)) is not None:
                    opcode, payload = frame
                    if opcode == 0x8:  # close
                        subscriber.send(payload, opcode=0x8)
                        break
                    if opcode == 0x9:  # ping
                        subscriber.send(payload, opcode=0xA)
                    elif opcode == 0x1:
                        message: Any = json.loads(payload)
                        if isinstance(message, list):
                            parts = cast("list[Any]", message)
                            if len(parts) > 1 and parts[0] == 5:
                                subscriber.topics.add(str(parts[1]))
            except (OSError, ValueError):
                pass
            finally:
                with replay.lock:
                    replay.subscribers.remove(subscriber)

        def _write(self) -> None:
            if not self._authorised():
                return
            time.sleep(latency)
            if self.path == "/mock/step" and self.command == "POST":
                self._send(HTTPStatus.OK, replay.advance())
                return
            body, raw = self._body()
            with replay.lock:
                replay.recorded.append({"method": self.command, "path": self.path, "body": body})
                if self.command == "PUT" and self.path == ITEM_SETS:
                    replay.item_sets = Raw(raw)  # stored as sent, byte for byte
                    status, answer = HTTPStatus.CREATED, None
                else:
                    status, answer = self._apply(body)
            self._send(status, answer)

        def _apply(self, body: Any) -> tuple[HTTPStatus, object]:
            """The client's behaviour for the writes the app makes; holds `replay.lock`."""
            match (self.command, self.path):
                case ("POST", path) if path == PAGES:
                    editable = sum(1 for p in replay.pages if p.get("isEditable"))
                    if editable >= replay.page_capacity:
                        return HTTPStatus.BAD_REQUEST, {"message": "Max pages reached"}
                    page_id = max((int(p["id"]) for p in replay.pages), default=100) + 1
                    page = {**body, "id": page_id, "isEditable": True}
                    replay.pages.append(page)
                    return HTTPStatus.OK, page
                case ("DELETE", path) if path.startswith(PAGES + "/"):
                    page_id = int(path.rsplit("/", 1)[1])
                    page = next((p for p in replay.pages if p["id"] == page_id), None)
                    if page is None:
                        return HTTPStatus.NOT_FOUND, {"message": "no such page"}
                    if not page.get("isEditable"):
                        return HTTPStatus.BAD_REQUEST, {"message": "page is not editable"}
                    replay.pages.remove(page)
                    return HTTPStatus.NO_CONTENT, None
                case ("PATCH", path) if path == SELECTION:
                    replay.spells = (body["spell1Id"], body["spell2Id"])
                    return HTTPStatus.NO_CONTENT, None
                case _:
                    return HTTPStatus.OK, {}

        def do_PUT(self) -> None:
            self._write()

        def do_POST(self) -> None:
            self._write()

        def do_PATCH(self) -> None:
            self._write()

        def do_DELETE(self) -> None:
            self._write()

    return Handler


def certificates(directory: Path) -> tuple[Path, Path]:
    """A root CA (`root.pem`, what the app trusts) and a 127.0.0.1 leaf signed by it.
    Returns (leaf chain, leaf key); the key is written with owner-only permissions."""
    now = dt.datetime.now(dt.UTC)
    root_key = ec.generate_private_key(ec.SECP256R1())
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "stronk lcu-mock root")])
    root = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(root_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()), False)
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, False, False),
            critical=True,
        )
        .sign(root_key, hashes.SHA256())
    )
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")]))
        .issuer_name(root_name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), False
        )
        .sign(root_key, hashes.SHA256())
    )
    pem = serialization.Encoding.PEM
    (directory / "root.pem").write_bytes(root.public_bytes(pem))
    chain = directory / "leaf.pem"
    chain.write_bytes(leaf.public_bytes(pem) + root.public_bytes(pem))
    key = directory / "leaf.key"
    fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(
            leaf_key.private_bytes(
                pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
        )
    return chain, key


@dataclass
class Mock:
    server: ThreadingHTTPServer
    replay: Replay
    lockfile: Path
    root: Path

    @property
    def port(self) -> int:
        return self.server.server_address[1]


def start(session: Path, directory: Path, port: int = 0, latency_ms: int = 0) -> Mock:
    """Serve in a background thread; `mock.server.shutdown()` stops it."""
    directory.mkdir(parents=True, exist_ok=True)
    replay = Replay.load(session)
    password = secrets.token_urlsafe(16)
    chain, key = certificates(directory)
    handler = make_handler(replay, password, latency_ms / 1000)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(chain, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    lockfile = directory / "lockfile"
    lockfile.write_text(f"LeagueClient:{os.getpid()}:{server.server_address[1]}:{password}:https")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return Mock(server, replay, lockfile, directory / "root.pem")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="A fake League client replaying a session")
    parser.add_argument("session", type=Path)
    parser.add_argument("--dir", type=Path, default=Path("runs/lcu-mock"))
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--latency-ms", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        mock = start(args.session, args.dir, args.port, args.latency_ms)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"lcu-mock: {e}", file=sys.stderr)
        return 1
    print(f"lcu-mock: https://127.0.0.1:{mock.port}  lockfile {mock.lockfile}  root {mock.root}")
    print(f"lcu-mock: {len(mock.replay.steps)} steps; POST /mock/step to advance; Ctrl-C stops")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        mock.server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

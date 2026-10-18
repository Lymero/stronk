"""A fake League client (docs/architecture.md, section 5): `just lcu-mock <session>`.

    lcu_mock.py <session.json> [--dir runs/lcu-mock] [--port 0] [--latency-ms 0]

Writes `lockfile` (the client's format) and `root.pem` into `--dir`, then serves HTTPS on
127.0.0.1 with a certificate chained to that root, like the real client. Requests need the
lockfile's password (Basic auth, user `riot`). The session file's steps are replayed one at a
time: `POST /mock/step` moves to the next, `GET /mock/state` says where it is. Every write the
app makes (PUT, POST, PATCH, DELETE outside `/mock/`) is recorded and listed by
`GET /mock/recorded`, so tests can check what was imported.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import ipaddress
import json
import os
import secrets
import ssl
import sys
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, override

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

SESSION = "/lol-champ-select/v1/session"
CHAMPIONS = "/lol-game-data/assets/v1/champion-summary.json"


@dataclass
class Replay:
    """The session file and how far it has been played."""

    steps: list[dict[str, Any]]
    champions: list[dict[str, Any]]
    step: int = 0
    recorded: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def load(cls, path: Path) -> Replay:
        data: dict[str, Any] = json.loads(path.read_text())
        steps: list[dict[str, Any]] = data["steps"]
        if not steps:
            raise ValueError(f"{path}: `steps` must be a non-empty list")
        champions: list[dict[str, Any]] = data.get("champions", [])
        return cls(steps=steps, champions=champions)

    def current(self) -> dict[str, Any]:
        with self.lock:
            return self.steps[self.step]

    def advance(self) -> dict[str, Any]:
        with self.lock:
            self.step = min(self.step + 1, len(self.steps) - 1)
            return {"step": self.step, "name": self.steps[self.step].get("name")}


def make_handler(replay: Replay, password: str, latency: float) -> type[BaseHTTPRequestHandler]:
    expected = "Basic " + base64.b64encode(f"riot:{password}".encode()).decode()

    class Handler(BaseHTTPRequestHandler):
        @override
        def log_message(self, format: str, *args: object) -> None:
            pass  # quiet: tests read /mock/recorded instead

        def _send(self, status: HTTPStatus, body: object | None = None) -> None:
            data = b"" if body is None else json.dumps(body).encode()
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

        def _body(self) -> object:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                return json.loads(raw) if raw else None
            except json.JSONDecodeError:
                return raw.decode(errors="replace")

        def do_GET(self) -> None:
            if not self._authorised():
                return
            time.sleep(latency)
            match self.path:
                case "/mock/state":
                    step = replay.current()
                    self._send(HTTPStatus.OK, {"step": replay.step, "name": step.get("name")})
                case "/mock/recorded":
                    with replay.lock:
                        self._send(HTTPStatus.OK, list(replay.recorded))
                case path if path == SESSION:
                    session = replay.current().get("session")
                    if session is None:  # what the client answers outside champion select
                        self._send(HTTPStatus.NOT_FOUND, {"message": "No active delegate"})
                    else:
                        self._send(HTTPStatus.OK, session)
                case path if path == CHAMPIONS:
                    self._send(HTTPStatus.OK, replay.champions)
                case _:
                    self._send(HTTPStatus.NOT_FOUND, {"message": f"not mocked: {self.path}"})

        def _write(self) -> None:
            if not self._authorised():
                return
            time.sleep(latency)
            if self.path == "/mock/step" and self.command == "POST":
                self._send(HTTPStatus.OK, replay.advance())
                return
            entry = {"method": self.command, "path": self.path, "body": self._body()}
            with replay.lock:
                replay.recorded.append(entry)
            self._send(HTTPStatus.OK, {})

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

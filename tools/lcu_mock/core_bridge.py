"""The UI in a browser against the real core (ADR-048): `just e2e` serves this for Playwright.

    core_bridge.py <session.json> --core <stronk-core> [--port 8790] [--dir runs/core-bridge]

Starts lcu-mock on the session and serves HTTP on 127.0.0.1 for the UI's `CoreBackend`:
`POST /run` with `{"id", "params"}` runs `stronk-core run` against lcu-mock and the signed
fixture data, and answers `{"ok": true, "value"}` or `{"ok": false, "error"}`, the shape of the
Backend port. For the tests: `POST /mock/step` moves the session on, `POST /mock/reset` starts a
fresh lcu-mock (account state and backups too), `GET /mock/recorded` lists the writes the core
made, `GET /mock/state` says which step is playing.

Test tooling only: it listens on 127.0.0.1 and runs nothing but the given core binary.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, override

from lcu_mock import Mock, start

ROOT = Path(__file__).resolve().parents[2]
MAX_BODY = 1 << 20


class Bridge:
    """One lcu-mock and the core run against it; `reset` replaces both's state."""

    def __init__(self, session: Path, core: Path, directory: Path) -> None:
        self.session = session
        self.core = core
        self.directory = directory
        self.lock = threading.Lock()
        self.mock = self._start()

    def _start(self) -> Mock:
        shutil.rmtree(self.directory, ignore_errors=True)
        return start(self.session, self.directory / "lcu-mock")

    def reset(self) -> dict[str, Any]:
        with self.lock:
            self.mock.server.shutdown()
            self.mock.server.server_close()
            self.mock = self._start()
            return {"step": 0}

    def run(self, command: str, params: object) -> dict[str, Any]:
        with self.lock:
            mock = self.mock
        env = {
            **os.environ,
            "STRONK_LCU_LOCKFILE": str(mock.lockfile),
            "STRONK_LCU_CERT": str(mock.root),
            "STRONK_DATA_DIR": str(ROOT / "fixtures/data"),
            "STRONK_DATA_KEY": str(ROOT / "fixtures/data.pub"),
            "STRONK_BACKUP_DIR": str(self.directory / "backups"),
            "STRONK_CACHE_DIR": str(self.directory / "cache"),
        }
        done = subprocess.run(  # noqa: S603 (our own binary, arguments as a list)
            [str(self.core), "run", command, "--params", json.dumps(params)],
            capture_output=True, text=True, env=env, timeout=30, check=False,
        )  # fmt: skip
        try:
            if done.returncode == 0:
                return {"ok": True, "value": json.loads(done.stdout)}
            return {"ok": False, "error": json.loads(done.stderr)}
        except json.JSONDecodeError:
            message = (done.stderr or done.stdout).strip() or f"exit code {done.returncode}"
            return {"ok": False, "error": {"code": "internal", "message": message}}


def make_handler(bridge: Bridge) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        @override
        def log_message(self, format: str, *args: object) -> None:
            pass

        def _send(self, status: HTTPStatus, body: object) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            replay = bridge.mock.replay
            match self.path:
                case "/mock/recorded":
                    with replay.lock:
                        self._send(HTTPStatus.OK, list(replay.recorded))
                case "/mock/state":
                    with replay.lock:
                        step = replay.steps[replay.step]
                        self._send(HTTPStatus.OK, {"step": replay.step, "name": step.get("name")})
                case _:
                    self._send(HTTPStatus.NOT_FOUND, {"message": f"no {self.path}"})

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"message": "body too large"})
                return
            raw = self.rfile.read(length) if length else b"{}"
            match self.path:
                case "/run":
                    try:
                        request: Any = json.loads(raw)
                        command, params = str(request["id"]), request.get("params", {})
                    except (json.JSONDecodeError, KeyError, TypeError):
                        self._send(HTTPStatus.BAD_REQUEST, {"message": "expected {id, params}"})
                        return
                    self._send(HTTPStatus.OK, bridge.run(command, params))
                case "/mock/step":
                    self._send(HTTPStatus.OK, bridge.mock.replay.advance())
                case "/mock/reset":
                    self._send(HTTPStatus.OK, bridge.reset())
                case _:
                    self._send(HTTPStatus.NOT_FOUND, {"message": f"no {self.path}"})

    return Handler


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="The real core against lcu-mock, over HTTP")
    parser.add_argument("session", type=Path)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--dir", type=Path, default=ROOT / "runs/core-bridge")
    args = parser.parse_args(argv)
    try:
        bridge = Bridge(args.session, args.core, args.dir)
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(bridge))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"core-bridge: {e}", file=sys.stderr)
        return 1
    print(f"core-bridge: http://127.0.0.1:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""Serve a data directory like the CDN will (ADR-017): `just serve-data`.

    serve_data.py [--root dist/data] [--host 127.0.0.1] [--port 8787]

Static files only, read-only. Strong ETags (sha256 of the bytes) with `If-None-Match` -> 304, so
the app's HTTP source and its cache can be exercised locally. JSON gets its content type and
CORS is open, since published data is public and the web viewer reads it from a browser.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import override

TYPES = {".json": "application/json", ".minisig": "text/plain; charset=utf-8"}


class DataHandler(SimpleHTTPRequestHandler):
    @override
    def guess_type(self, path: str | os.PathLike[str]) -> str:
        return TYPES.get(Path(path).suffix, super().guess_type(path))

    @override
    def do_GET(self) -> None:
        self._respond(body=True)

    @override
    def do_HEAD(self) -> None:
        self._respond(body=False)

    def _respond(self, *, body: bool) -> None:
        path = Path(self.translate_path(self.path))  # resolves inside the root only
        if not path.is_file() or any(part.startswith(".") for part in Path(self.path).parts):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        etag = f'"{hashlib.sha256(data).hexdigest()}"'
        if etag in {t.strip() for t in self.headers.get("If-None-Match", "").split(",")}:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            self._common_headers()
            self.end_headers()
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("ETag", etag)
        self._common_headers()
        self.end_headers()
        if body:
            self.wfile.write(data)

    def _common_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")  # always revalidate, as against the CDN
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Expose-Headers", "ETag")


def server(root: Path, host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), partial(DataHandler, directory=str(root)))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Serve a data directory like the CDN will")
    parser.add_argument("--root", type=Path, default=Path("dist/data"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    if not args.root.is_dir():
        print(f"serve-data: no directory at {args.root}; publish first", file=sys.stderr)
        return 1
    httpd = server(args.root, args.host, args.port)
    print(f"serve-data: {args.root} on http://{args.host}:{httpd.server_port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

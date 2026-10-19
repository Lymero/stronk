"""Serve public/ on 127.0.0.1 like Cloudflare: /method is method.html, unknown paths 404.html."""

import argparse
import http.server
import sys
from pathlib import Path

ROOT = Path(__file__).parent / "public"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)  # type: ignore[arg-type]

    def send_head(self):  # type: ignore[no-untyped-def]
        path = self.path.split("?", 1)[0].rstrip("/")
        if path and "." not in Path(path).name and (ROOT / f"{path.lstrip('/')}.html").is_file():
            self.path = f"{path}.html"
        elif path and not (ROOT / path.lstrip("/")).exists():
            body = (ROOT / "404.html").read_bytes()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return None
        return super().send_head()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8788)
    port = parser.parse_args().port
    sys.stderr.write(f"http://127.0.0.1:{port}\n")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()

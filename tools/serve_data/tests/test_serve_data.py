import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
import serve_data


@pytest.fixture
def base(tmp_path: Path) -> Iterator[str]:
    (tmp_path / "16.20" / "all").mkdir(parents=True)
    (tmp_path / "16.20" / "all" / "b.json").write_bytes(b'{"a":1}\n')
    (tmp_path / "16.20" / ".hidden").write_bytes(b"secret")
    (tmp_path.parent / "outside.json").write_bytes(b"nope")
    httpd = serve_data.server(tmp_path, "127.0.0.1", 0)
    thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


def get(url: str, **headers: str) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, headers=headers)  # noqa: S310 (local test server)
    try:
        with urllib.request.urlopen(request, timeout=5) as r:  # noqa: S310
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), b""


def test_serves_json_with_an_etag(base: str) -> None:
    status, headers, body = get(f"{base}/16.20/all/b.json")
    assert status == 200
    assert body == b'{"a":1}\n'
    assert headers["Content-Type"] == "application/json"
    assert headers["ETag"].startswith('"')
    assert headers["Access-Control-Allow-Origin"] == "*"


def test_matching_etag_is_not_modified(base: str) -> None:
    _, headers, _ = get(f"{base}/16.20/all/b.json")
    status, again, body = get(f"{base}/16.20/all/b.json", **{"If-None-Match": headers["ETag"]})
    assert status == 304
    assert body == b""
    assert again["ETag"] == headers["ETag"]


@pytest.mark.parametrize("path", ["/16.20/.hidden", "/../outside.json", "/16.20/", "/missing"])
def test_hidden_outside_and_missing_are_not_found(base: str, path: str) -> None:
    assert get(f"{base}{path}")[0] == 404

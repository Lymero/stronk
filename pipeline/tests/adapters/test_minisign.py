import stat
from pathlib import Path

import pytest

from stronk_pipeline.adapters import minisign
from stronk_pipeline.domain.result import Err, Ok

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"


def signer(tmp_path: Path) -> minisign.MinisignSigner:
    result = minisign.generate(tmp_path / "k.key")
    assert isinstance(result, Ok)
    return result.value


def test_signature_round_trip(tmp_path: Path) -> None:
    s = signer(tmp_path)
    signature = s.sign(b"manifest", "stronk manifest v1 patch=16.20 runId=r")
    assert minisign.verify(s.public_key(), b"manifest", signature) == Ok(
        "stronk manifest v1 patch=16.20 runId=r"
    )


def test_tampered_message_comment_or_key_is_rejected(tmp_path: Path) -> None:
    s, other = signer(tmp_path), signer(tmp_path / "other")
    signature = s.sign(b"manifest", "patch=16.20")
    assert minisign.verify(s.public_key(), b"manifesT", signature) == Err("bad signature")
    forged = signature.replace(b"patch=16.20", b"patch=16.21")
    assert minisign.verify(s.public_key(), b"manifest", forged) == Err("bad signature")
    assert minisign.verify(other.public_key(), b"manifest", signature) == Err(
        "signed by another key"
    )
    assert isinstance(minisign.verify(s.public_key(), b"manifest", b"garbage"), Err)


def test_key_round_trip_and_id_format(tmp_path: Path) -> None:
    s = signer(tmp_path)
    loaded = minisign.load(tmp_path / "k.key")
    assert isinstance(loaded, Ok)
    assert loaded.value.key_id == s.key_id
    assert loaded.value.public_key() == s.public_key()
    assert s.key_id == s.keynum[::-1].hex().upper()  # minisign's little-endian u64
    assert f"public key {s.key_id}" in s.public_key()


def test_key_file_is_owner_only_and_never_overwritten(tmp_path: Path) -> None:
    signer(tmp_path)
    assert stat.S_IMODE((tmp_path / "k.key").stat().st_mode) == 0o600
    again = minisign.generate(tmp_path / "k.key")
    assert isinstance(again, Err)
    assert "refusing to overwrite" in again.error.message


@pytest.mark.parametrize(
    "content",
    [
        "",
        "something else\n",
        "stronk signing key v1\nkey_id=00\nseed=AAAA\n",
        "stronk signing key v1\n",
    ],
)
def test_bad_key_files_are_invalid_without_echoing_them(content: str, tmp_path: Path) -> None:
    (tmp_path / "k.key").write_text(content)
    result = minisign.load(tmp_path / "k.key")
    assert isinstance(result, Err)
    assert result.error.kind == "invalid"
    assert "AAAA" not in result.error.message


def test_multiline_trusted_comment_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="one line"):
        signer(tmp_path).sign(b"m", "a\nb")


def test_committed_example_signature_verifies() -> None:
    """The same file the Rust contract test verifies with minisign-verify."""
    result = minisign.verify(
        (CONTRACTS / "tests" / "keys" / "test-only.pub").read_text(),
        (CONTRACTS / "examples" / "manifest.v1.json").read_bytes(),
        (CONTRACTS / "examples" / "manifest.v1.json.minisig").read_bytes(),
    )
    assert result == Ok("stronk manifest v1 patch=26.20 runId=2026-10-16T1200-a1b2c3")

from pathlib import Path

from stronk_pipeline.adapters import minisign
from stronk_pipeline.adapters.minisign import MinisignKeys
from stronk_pipeline.application.signing_keygen import KeygenParams, signing_keygen_command
from stronk_pipeline.domain.result import Err, Ok


def test_creates_a_key_and_its_public_half(tmp_path: Path) -> None:
    command = signing_keygen_command(MinisignKeys())
    result = command.run(KeygenParams(out=str(tmp_path / "keys" / "signing.key")))
    assert isinstance(result, Ok)
    public = (tmp_path / "keys" / "signing.key.pub").read_text()
    assert public == result.value.public_key
    assert result.value.key_id in public
    loaded = minisign.load(tmp_path / "keys" / "signing.key")
    assert isinstance(loaded, Ok)
    signature = loaded.value.sign(b"data", "c")
    assert minisign.verify(public, b"data", signature) == Ok("c")


def test_never_replaces_an_existing_key(tmp_path: Path) -> None:
    command = signing_keygen_command(MinisignKeys())
    params = KeygenParams(out=str(tmp_path / "signing.key"))
    command.run(params)
    before = (tmp_path / "signing.key").read_bytes()
    again = command.run(params)
    assert isinstance(again, Err)
    assert (tmp_path / "signing.key").read_bytes() == before

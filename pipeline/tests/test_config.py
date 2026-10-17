import pytest

from stronk_pipeline.config import Settings


def test_api_key_is_never_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_key = "-".join(["RGAPI", "0" * 8, "0" * 4, "0" * 4, "0" * 4, "0" * 12])
    monkeypatch.setenv("RIOT_API_KEY", fake_key)
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.riot_api_key is not None
    assert "RGAPI" not in repr(settings)
    assert "RGAPI" not in settings.model_dump_json()

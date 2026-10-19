"""Schemas, examples and generated Python models agree."""

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from pydantic import BaseModel, ValidationError

from stronk_contracts.build_v1 import Build
from stronk_contracts.index_v1 import Index
from stronk_contracts.manifest_v1 import Manifest

CONTRACTS = Path(__file__).resolve().parents[1]
CASES: list[tuple[str, type[BaseModel]]] = [
    ("build.v1", Build),
    ("index.v1", Index),
    ("manifest.v1", Manifest),
]

INVALID: dict[str, list[tuple[tuple[str | int, ...], Any]]] = {
    "build.v1": [
        (("schemaVersion",), 2),
        (("patch",), "26"),
        (("role",), "SUPPORT"),
        (("region",), "EUW1"),
        (("items", 0, "slot"), 7),
        (("items", 2, "flags", 0), "unknown_flag"),
        (("items", 0, "ci"), [0.1]),
        (("runes", 0, "page", "perks"), [1, 2, 3]),
        (("extra",), True),
    ],
    "index.v1": [
        (("schemaVersion",), 2),
        (("patches", 0), "../26.19"),
        (("patches",), "26.20"),
        (("extra",), True),
    ],
    "manifest.v1": [
        (("files", 0, "path"), "../escape.json"),
        (("files", 0, "path"), "/absolute.json"),
        (("files", 0, "path"), "euw1/./x.json"),
        (("files", 0, "sha256"), "ABC"),
        (("keyId",), "0123456789abcdef"),
        (("runId",), "bad id"),
        (("generatedAt",), "yesterday"),
    ],
}


def load(name: str, kind: str) -> Any:
    folder = "schemas" if kind == "schema" else "examples"
    suffix = ".schema.json" if kind == "schema" else ".json"
    return json.loads((CONTRACTS / folder / f"{name}{suffix}").read_text())


def validator(name: str) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(
        load(name, "schema"), format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER
    )


def mutate(value: Any, path: tuple[str | int, ...], replacement: Any) -> Any:
    value = copy.deepcopy(value)
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    return value


@pytest.mark.parametrize(("name", "model"), CASES)
def test_schema_is_valid_draft_2020_12(name: str, model: type[BaseModel]) -> None:
    jsonschema.Draft202012Validator.check_schema(load(name, "schema"))


@pytest.mark.parametrize(("name", "model"), CASES)
def test_example_matches_schema_and_model(name: str, model: type[BaseModel]) -> None:
    example = load(name, "example")
    validator(name).validate(example)  # pyright: ignore[reportUnknownMemberType]
    parsed = model.model_validate(example)
    assert parsed.model_dump(mode="json", by_alias=True, exclude_unset=True) == example


@pytest.mark.parametrize(
    ("name", "path", "bad"), [(n, p, b) for n, cases in INVALID.items() for p, b in cases]
)
def test_invalid_values_rejected_by_schema_and_model(
    name: str, path: tuple[str | int, ...], bad: Any
) -> None:
    value = mutate(load(name, "example"), path, bad)
    model = dict(CASES)[name]
    assert not validator(name).is_valid(value)  # pyright: ignore[reportUnknownMemberType]
    with pytest.raises(ValidationError):
        model.model_validate(value)


def test_published_fixture_builds_validate() -> None:
    """`publish`'s real output (fixtures/data) follows the schema, optional fields included."""
    files = sorted((CONTRACTS.parent / "fixtures/data").glob("*/*/*/*/*.json"))
    assert len(files) > 10
    check = validator("build.v1")
    for path in files:
        check.validate(json.loads(path.read_text()))  # pyright: ignore[reportUnknownMemberType]

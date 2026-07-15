"""Validation errors carry their coordinate as data and still read exactly as before."""

from dataclasses import dataclass, field
from typing import Annotated

import pytest

from pytypehint import (
    Max, SchemaTypeError, SchemaValueError, signature_of, struct_of,
)


@dataclass(frozen=True)
class Page:
    size: Annotated[int, Max(100)] = 20


@dataclass
class Search:
    query: str
    page: Page = Page()
    tags: list[int] = field(default_factory=list)


@dataclass
class File:
    path: str


@dataclass
class Url:
    value: str


@dataclass
class Source:
    value: File | Url


def _search(data):
    return struct_of(Search).build(data)


def _build_impure_default():
    """Certification serves 1 and passes; the build serves 2 and fails.

    The counter is per call: a shared one would drift past certification and turn
    this into a compile-time error instead of the serving error under test.
    """
    counter = iter(range(1, 99))

    @dataclass
    class Leaf:
        n: Annotated[int, Max(1)] = field(default_factory=lambda: next(counter))

    @dataclass
    class Root:
        leaf: Leaf

    return struct_of(Root).build({"leaf": {}})


def run(page: Page):
    """A plain function for the Signature path."""


# (label, call, expected class, expected str, expected path)
_CASES = [
    (
        "nested",
        lambda: _search({"query": "q", "page": {"size": 500}}),
        SchemaValueError,
        "page: size: too large: 500, maximum 100",
        ("page", "size"),
    ),
    (
        "list",
        lambda: _search({"query": "q", "tags": [1, "no", 3]}),
        SchemaTypeError,
        "tags: [1]: expected int, got str",
        ("tags", 1),
    ),
    (
        "default",
        _build_impure_default,
        SchemaValueError,
        "leaf: n: default: too large: 2, maximum 1",
        ("leaf", "n", "default"),
    ),
    (
        "$type",
        lambda: struct_of(Source).build({"value": {"$type": 1, "value": "u"}}),
        SchemaTypeError,
        "value: $type: expected str, got int",
        ("value", "$type"),
    ),
    (
        "signature",
        lambda: signature_of(run).build({"page": {"size": 500}}),
        SchemaValueError,
        "page: size: too large: 500, maximum 100",
        ("page", "size"),
    ),
]

_IDS = [case[0] for case in _CASES]


@pytest.mark.parametrize("label, call, cls, text, path", _CASES, ids=_IDS)
def test_message_is_unchanged(label, call, cls, text, path):
    """README, 'Guarantees': 'Errors retain the complete field and list-index path, as the message text'."""
    with pytest.raises(cls) as error:
        call()

    assert str(error.value) == text


@pytest.mark.parametrize("label, call, cls, text, path", _CASES, ids=_IDS)
def test_path_is_a_tuple_of_segments(label, call, cls, text, path):
    """README, 'Guarantees': errors carry the path 'as data: SchemaTypeError and SchemaValueError carry `path`'."""
    with pytest.raises(cls) as error:
        call()

    assert error.value.path == path
    assert type(error.value.path) is tuple


@pytest.mark.parametrize("label, call, cls, text, path", _CASES, ids=_IDS)
def test_leaf_is_the_message_without_the_path(label, call, cls, text, path):
    """README, 'Guarantees': the errors 'carry `path` and `leaf`' — leaf is the reason alone."""
    with pytest.raises(cls) as error:
        call()

    rendered = "".join(f"[{s}]: " if type(s) is int else f"{s}: " for s in path)
    assert error.value.leaf == text[len(rendered):]
    assert rendered + error.value.leaf == text


@pytest.mark.parametrize("label, call, cls, text, path", _CASES, ids=_IDS)
def test_error_is_the_schema_class(label, call, cls, text, path):
    """README, 'Public API': every validation failure is a `SchemaTypeError` or a `SchemaValueError`."""
    with pytest.raises(Exception) as error:
        call()

    assert type(error.value) is cls


@pytest.mark.parametrize("label, call, cls, text, path", _CASES, ids=_IDS)
def test_existing_handlers_still_catch(label, call, cls, text, path):
    """README, 'Guarantees': the schema errors 'subclass `TypeError` and `ValueError`', so code written before them keeps working."""
    builtin = TypeError if issubclass(cls, TypeError) else ValueError

    with pytest.raises(builtin):
        call()

    with pytest.raises((TypeError, ValueError)):
        call()


# ------------------------------------------------------- path shape details


def test_list_indexes_are_integers_not_text():
    """README, 'Guarantees': the path is data — an index is an int a wrapper can use to subscript."""
    with pytest.raises(SchemaTypeError) as error:
        _search({"query": "q", "tags": [1, "no"]})

    assert error.value.path[1] == 1
    assert type(error.value.path[1]) is int


def test_default_is_a_plain_segment():
    """docs/restrictions.md, 'Impure default': 'leaf: n: default: too large: 2, maximum 1' — 'default' is a path segment, not part of the reason."""
    with pytest.raises(SchemaValueError) as error:
        _build_impure_default()

    assert error.value.path[-1] == "default"
    assert error.value.leaf.startswith("too large")


def test_type_is_a_plain_segment():
    """docs/build.md: 'value: $type: expected str, got int' — the discriminator is its own coordinate."""
    with pytest.raises(SchemaTypeError) as error:
        struct_of(Source).build({"value": {"$type": 1, "value": "u"}})

    assert error.value.path == ("value", "$type")
    assert error.value.leaf == "expected str, got int"


def test_a_top_level_failure_has_an_empty_path():
    """README, 'Guarantees': the path runs from the root of the input; a failure at the root has no segments."""
    with pytest.raises(SchemaTypeError) as error:
        struct_of(Search).build({"query": "q", "nope": 1})

    assert error.value.path == ()
    assert error.value.leaf == "unexpected key(s): nope"
    assert str(error.value) == "unexpected key(s): nope"


def test_rendering_is_reproducible_from_path_and_leaf():
    """README, 'Guarantees': the text and the data are two views of one error, not two sources of truth."""
    with pytest.raises(SchemaValueError) as error:
        _search({"query": "q", "page": {"size": 500}})

    rebuilt = SchemaValueError(error.value.leaf, error.value.path)

    assert str(rebuilt) == str(error.value)


def test_schema_errors_are_constructible_with_a_leaf_alone():
    """README, 'Public API': the classes are exported, so a wrapper can raise them for its own coercion failures."""
    error = SchemaTypeError("expected int, got str")

    assert error.path == ()
    assert error.leaf == "expected int, got str"
    assert str(error) == "expected int, got str"


def test_schema_error_classes_are_distinct_hierarchies():
    """README, 'Public API': the two classes exist so a caller can tell a wrong type from a broken constraint."""
    assert issubclass(SchemaTypeError, TypeError)
    assert issubclass(SchemaValueError, ValueError)
    assert not issubclass(SchemaTypeError, ValueError)
    assert not issubclass(SchemaValueError, TypeError)

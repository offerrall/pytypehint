from dataclasses import dataclass, field, make_dataclass

import pytest

from pytypehint import struct_of


@dataclass
class A:
    x: int = 0


@dataclass
class B:
    y: str = ""


@dataclass
class Choice:
    value: A | B


def test_discriminator_missing_unknown_and_wrong_type():
    schema = struct_of(Choice)
    with pytest.raises(TypeError, match=r'ambiguous dict: field accepts A \| B — add "\$type" naming the variant'):
        schema.resolve({"value": {"x": 1}})
    with pytest.raises(ValueError, match=r"value: \$type: not a choice: 'C', expected one of \('A', 'B'\)"):
        schema.resolve({"value": {"$type": "C"}})
    with pytest.raises(TypeError, match=r"value: \$type: expected str, got int"):
        schema.resolve({"value": {"$type": 1}})


def test_resolve_preserves_and_build_consumes_discriminator():
    data = {"value": {"$type": "B", "y": "ok"}}
    assert struct_of(Choice).resolve(data) == data
    assert struct_of(Choice).build(data) == Choice(B("ok"))


def test_discriminator_nested_and_in_list_union():
    @dataclass
    class Outer:
        choice: Choice
        items: list[A | B]

    built = struct_of(Outer).build({
        "choice": {"value": {"$type": "A", "x": 2}},
        "items": [{"$type": "B", "y": "z"}],
    })
    assert built == Outer(Choice(A(2)), [B("z")])


def test_list_union_discriminator_errors_include_index_path():
    @dataclass
    class Batch:
        items: list[A | B]

    schema = struct_of(Batch)
    with pytest.raises(TypeError, match=r'items: \[0\]: ambiguous dict: field accepts A \| B — add "\$type" naming the variant'):
        schema.build({"items": [{"x": 1}]})
    with pytest.raises(ValueError, match=r"items: \[0\]: \$type: not a choice: 'C', expected one of \('A', 'B'\)"):
        schema.build({"items": [{"$type": "C"}]})


def test_list_union_default_is_fresh_and_builds_variants():
    @dataclass
    class Batch:
        items: list[A | B] = field(default_factory=lambda: [A(1), B("x")])

    schema = struct_of(Batch)
    first = schema.build({})
    second = schema.build({})
    assert first == second == Batch([A(1), B("x")])
    assert first.items is not second.items
    assert first.items[0] is not second.items[0]


def test_discriminator_on_unambiguous_struct_is_unexpected_key():
    @dataclass
    class One:
        value: A

    with pytest.raises(TypeError, match=r"value: unexpected key\(s\): \$type"):
        struct_of(One).resolve({"value": {"$type": "A", "x": 1}})


def test_duplicate_discriminator_names_are_rejected_at_compilation():
    first = make_dataclass("Same", [("x", int)])
    second = make_dataclass("Same", [("y", str)])
    root = make_dataclass("Root", [("value", first | second)])

    with pytest.raises(
            ValueError,
            match=r"Field 'value': duplicate discriminator name\(s\): Same"):
        struct_of(root)


def test_duplicate_discriminator_names_in_list_are_rejected_at_compilation():
    first = make_dataclass("Same", [("x", int)])
    second = make_dataclass("Same", [("y", str)])
    root = make_dataclass("Root", [("values", list[first | second])])

    with pytest.raises(
            ValueError,
            match=r"Field 'values': duplicate discriminator name\(s\): Same"):
        struct_of(root)

from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated, Literal

import pytest

from pytypehint.atoms import Choices, Label, Max, MultipleOf, Placeholder, Slider
from pytypehint.bridge import struct_of
from pytypehint.shapes import EnumShape, Int, NoneShape, Str


def test_literal_str_compiles_to_str_choices():
    @dataclass
    class C:
        lang: Literal["en", "es"] = "en"

    schema = struct_of(C)
    assert schema.fields[0].shape == (Str(choices=Choices(values=("en", "es"))),)
    assert schema.resolve({"lang": "en"}) == {"lang": "en"}
    with pytest.raises(ValueError, match="not a choice"):
        schema.resolve({"lang": "fr"})
    with pytest.raises(TypeError, match="expected str"):
        schema.resolve({"lang": 1})


def test_literal_int_compiles_to_int_choices():
    @dataclass
    class C:
        n: Literal[1, 2] = 1

    schema = struct_of(C)
    assert schema.fields[0].shape == (Int(choices=Choices(values=(1, 2))),)
    assert schema.resolve({"n": 1}) == {"n": 1}
    with pytest.raises(ValueError, match="not a choice"):
        schema.resolve({"n": 3})


def test_literal_float_rejected():
    @dataclass
    class C:
        x: Literal[0.5, 1.0] = 0.5

    # PEP 586: Literal does not carry floats; the message points to the alias
    with pytest.raises(TypeError, match="Literal values must be int or str, got float"):
        struct_of(C)


def test_literal_mixed_types_rejected():
    @dataclass
    class C:
        x: Literal["a", 1] = "a"

    with pytest.raises(TypeError, match="same type"):
        struct_of(C)


def test_literal_bool_rejected():
    @dataclass
    class C:
        x: Literal[True] = True

    with pytest.raises(TypeError, match="must be int or str"):
        struct_of(C)


def test_literal_none_rejected():
    @dataclass
    class C:
        x: Literal[None] = None

    with pytest.raises(TypeError, match="must be int or str"):
        struct_of(C)


def test_literal_both_bool_rejected():
    @dataclass
    class C:
        x: Literal[True, False] = True

    with pytest.raises(TypeError, match="must be int or str"):
        struct_of(C)


def test_literal_duplicates_collapsed_by_python():
    @dataclass
    class C:
        x: Literal["a", "a"] = "a"

    assert struct_of(C).fields[0].shape == (Str(choices=Choices(values=("a",))),)


def test_literal_meta_reinjection():
    @dataclass
    class C:
        x: Annotated[Literal["a", "b"], Placeholder("pick")] = "a"

    shape = struct_of(C).fields[0].shape[0]
    assert shape == Str(choices=Choices(values=("a", "b")), placeholder=Placeholder("pick"))


def test_literal_explicit_choices_rejected():
    @dataclass
    class C:
        x: Annotated[Literal["a"], Choices(values=("b",))] = "a"

    with pytest.raises(TypeError, match="already defines its choices"):
        struct_of(C)


def test_literal_delegated_max_cross_check():
    @dataclass
    class C:
        n: Annotated[Literal[1, 2, 3], Max(2)] = 1

    with pytest.raises(ValueError, match="above maximum"):
        struct_of(C)


def test_literal_delegated_multiple_of_ok():
    @dataclass
    class C:
        n: Annotated[Literal[5, 10], MultipleOf(5)] = 5

    struct_of(C)


def test_literal_delegated_multiple_of_fails():
    @dataclass
    class C:
        n: Annotated[Literal[5, 7], MultipleOf(5)] = 5

    with pytest.raises(ValueError, match="not a multiple"):
        struct_of(C)


def test_literal_unsupported_metadata_delegates():
    @dataclass
    class C:
        x: Annotated[Literal["a"], Slider()] = "a"

    with pytest.raises(TypeError, match="unsupported metadata"):
        struct_of(C)


def test_literal_union_with_none():
    @dataclass
    class C:
        x: Literal["a", "b"] | None = None

    schema = struct_of(C)
    assert schema.fields[0].shape == (Str(choices=Choices(values=("a", "b"))), NoneShape())
    assert schema.resolve({"x": None}) == {"x": None}
    assert schema.resolve({"x": "a"}) == {"x": "a"}


def test_literal_in_list():
    @dataclass
    class C:
        xs: list[Literal["a", "b"]] = field(default_factory=list)

    schema = struct_of(C)
    assert schema.resolve({"xs": ["a"]}) == {"xs": ["a"]}
    with pytest.raises(ValueError, match=r"\[0\]: not a choice"):
        schema.resolve({"xs": ["c"]})


def test_literal_field_level_atoms_split():
    @dataclass
    class C:
        lang: Annotated[Literal["en", "es"], Label("Language"), Placeholder("pick one")] = "en"

    (f,) = struct_of(C).fields
    assert f.label == Label("Language")
    assert f.shape[0] == Str(choices=Choices(values=("en", "es")), placeholder=Placeholder("pick one"))


def test_literal_is_sugar_equal_to_hand_written():
    @dataclass
    class Sugar:
        x: Literal["a", "b"] = "a"

    @dataclass
    class Hand:
        x: Annotated[str, Choices(values=("a", "b"))] = "a"

    assert repr(struct_of(Sugar).fields[0]) == repr(struct_of(Hand).fields[0])


def test_literal_default_valid():
    @dataclass
    class C:
        lang: Literal["en", "es"] = "en"

    struct_of(C)


def test_literal_default_invalid_fails():
    @dataclass
    class C:
        lang: Literal["en", "es"] = "fr"

    with pytest.raises(ValueError, match="not a choice"):
        struct_of(C)


def test_enum_now_supported():
    class Color(Enum):
        RED = 1

    @dataclass
    class C:
        c: Color = Color.RED

    assert isinstance(struct_of(C).fields[0].shape[0], EnumShape)

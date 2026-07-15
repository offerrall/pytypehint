from dataclasses import dataclass
from typing import Annotated

import pytest

from pytypehint import Description, Label, Min, struct_of
from pytypehint.shapes import Int, Str


Percent = Annotated[int, Min(0), Label("Pct")]


def test_label_in_alias_hoisted_from_union_option():
    @dataclass
    class C:
        x: Percent | str = 0

    f = struct_of(C).fields[0]
    assert f.label == Label("Pct")
    assert type(f.shape[0]) is Int
    assert f.shape[0].min == Min(0)
    assert type(f.shape[1]) is Str


def test_plain_alias_field_unchanged():
    @dataclass
    class C:
        x: Percent = 0

    assert struct_of(C).fields[0].label == Label("Pct")


def test_same_label_both_options_hoisted_once():
    @dataclass
    class C:
        x: Annotated[int, Label("A")] | Annotated[str, Label("A")] = 0

    assert struct_of(C).fields[0].label == Label("A")


def test_conflicting_labels_across_options_rejected():
    @dataclass
    class C:
        x: Annotated[int, Label("A")] | Annotated[str, Label("B")] = 0

    with pytest.raises(TypeError, match="x: conflicting labels across union options: 'A' vs 'B'"):
        struct_of(C)


def test_outer_label_overrides_hoisted():
    @dataclass
    class C:
        y: Annotated[Percent | str, Label("Outer")] = 0

    assert struct_of(C).fields[0].label == Label("Outer")


def test_description_hoisted_from_union_option():
    Money = Annotated[int, Description("Money")]

    @dataclass
    class C:
        x: Money | str = 0

    assert struct_of(C).fields[0].description == Description("Money")


def test_conflicting_descriptions_across_options_rejected():
    @dataclass
    class C:
        x: Annotated[int, Description("X")] | Annotated[str, Description("Y")] = 0

    with pytest.raises(TypeError, match="x: conflicting descriptions across union options: 'X' vs 'Y'"):
        struct_of(C)


def test_type_atoms_still_per_option():
    @dataclass
    class C:
        x: Annotated[int, Min(0)] | str = 0

    f = struct_of(C).fields[0]
    assert f.shape[0].min == Min(0)
    assert type(f.shape[1]) is Str


def test_type_atom_on_whole_union_still_rejected():
    @dataclass
    class C:
        x: Annotated[int | str, Min(0)] = 0

    with pytest.raises(TypeError, match="metadata on a union of multiple types must go per option"):
        struct_of(C)


def test_label_hoisted_through_optional():
    @dataclass
    class C:
        x: Percent | None = None

    f = struct_of(C).fields[0]
    assert f.label == Label("Pct")
    assert f.shape[0].min == Min(0)

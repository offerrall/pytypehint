from dataclasses import dataclass, field
from typing import Annotated, Optional

import pytest

from pytypehint import Label, Max, Min, signature_of, struct_of
from pytypehint.shapes import Int, NoneShape


def test_metadata_over_optional_compiles_and_validates():
    @dataclass
    class C:
        n: Annotated[int | None, Min(0)] = None

    s = struct_of(C)
    assert s.resolve({"n": None}) == {"n": None}
    assert s.resolve({"n": 5}) == {"n": 5}
    with pytest.raises(ValueError, match="too small"):
        s.resolve({"n": -1})
    with pytest.raises(TypeError, match="expected int"):
        s.resolve({"n": "5"})


def test_both_spellings_are_structurally_equal():
    @dataclass
    class Veiled:
        n: Annotated[int | None, Min(0)] = None

    @dataclass
    class Canonical:
        n: Annotated[int, Min(0)] | None = None

    assert repr(struct_of(Veiled).fields[0]) == repr(struct_of(Canonical).fields[0])


def test_typing_optional_spelling_also_compiles():
    @dataclass
    class C:
        n: Annotated[Optional[int], Min(0)] = None

    assert struct_of(C).resolve({"n": 3}) == {"n": 3}


def test_layering_through_the_veil():
    Percent = Annotated[int, Min(0), Max(100)]

    @dataclass
    class C:
        n: Annotated[Percent | None, Max(50)] = None

    f = struct_of(C).fields[0]
    assert type(f.shape[0]) is Int
    assert f.shape[0].min == Min(0)
    assert f.shape[0].max == Max(50)
    assert type(f.shape[1]) is NoneShape


def test_field_atoms_compose_with_transparency():
    @dataclass
    class C:
        age: Annotated[int | None, Min(0), Label("Age")] = None

    f = struct_of(C).fields[0]
    assert f.label == Label("Age")
    assert f.shape[0].min == Min(0)
    assert type(f.shape[1]) is NoneShape


def test_two_real_types_still_rejected():
    @dataclass
    class C:
        n: Annotated[int | str, Min(0)] = 0

    with pytest.raises(TypeError, match="metadata on a union of multiple types must go per option"):
        struct_of(C)


def test_none_does_not_reduce_two_real_types_to_one():
    @dataclass
    class C:
        n: Annotated[int | str | None, Min(0)] = None

    with pytest.raises(TypeError, match="metadata on a union of multiple types must go per option"):
        struct_of(C)


def test_list_item_union_compiles():
    @dataclass
    class C:
        ns: list[int | None] = field(default_factory=list)

    assert type(struct_of(C).fields[0].shape[0].item) is tuple


def test_list_item_annotated_union_rejects_ambiguous_metadata():
    @dataclass
    class C:
        ns: list[Annotated[int | str, Min(0)]] = field(default_factory=list)

    with pytest.raises(TypeError, match="metadata on a union of multiple types"):
        struct_of(C)


def test_bare_list_item_union_compiles():
    @dataclass
    class C:
        ns: list[int | str] = field(default_factory=list)

    assert type(struct_of(C).fields[0].shape[0].item) is tuple


def test_metadata_on_none_has_its_own_error():
    @dataclass
    class M:
        x: Annotated[None, Min(0)] = None

    with pytest.raises(TypeError, match="x: metadata on None: None is optionality, not a type"):
        struct_of(M)


def test_metadata_on_none_in_signature_param():
    def fn(y: Annotated[None, Min(0)] = None):
        ...

    with pytest.raises(TypeError, match="y: metadata on None: None is optionality, not a type"):
        signature_of(fn)


def test_none_shape_receives_no_atoms():
    @dataclass
    class C:
        n: Annotated[int | None, Min(0), Max(9)] = None

    shapes = struct_of(C).fields[0].shape
    none_shape = next(s for s in shapes if type(s) is NoneShape)
    assert none_shape == NoneShape()


# None-transparency is about the metadata, not the option order: a user who
# writes None first gets None first. (Distinct metadata Min(3) here keeps the
# `Annotated[None | int, ...]` object from interning with the int-first
# `Annotated[int | None, Min(0)]` forms above — typing caches Annotated by
# base+metadata and unions compare order-independently.)
def test_none_first_preserves_option_order():
    @dataclass
    class C:
        n: Annotated[None | int, Min(3)] = None

    assert [type(s).__name__ for s in struct_of(C).fields[0].shape] == ["NoneShape", "Int"]


def test_none_first_veiled_equals_bare_none_first():
    @dataclass
    class Veiled:
        n: Annotated[None | int, Min(3)] = None

    @dataclass
    class Canonical:
        n: None | Annotated[int, Min(3)] = None

    assert repr(struct_of(Veiled).fields[0]) == repr(struct_of(Canonical).fields[0])


def test_conflict_error_carries_field_name():
    @dataclass
    class C:
        amount: Annotated[int, Label("A")] | Annotated[str, Label("B")] = 0

    with pytest.raises(TypeError, match="amount: conflicting labels across union options: 'A' vs 'B'"):
        struct_of(C)

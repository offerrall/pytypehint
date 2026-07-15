from dataclasses import dataclass, field
from typing import Annotated, TypeAlias, get_args

import pytest

from pytypehint.atoms import Description, Label, Max, Min, Slider
from pytypehint.bridge import struct_of
from pytypehint.shapes import Int, List


def test_flatten_puts_outer_metadata_last():
    hint = Annotated[Annotated[int, Min(value=0), Max(value=100)], Max(value=50)]
    assert get_args(hint) == (int, Min(value=0), Max(value=100), Max(value=50))


def test_flatten_three_layers_keeps_layer_order():
    hint = Annotated[
        Annotated[Annotated[int, Min(value=0)], Max(value=100)],
        Min(value=10),
    ]
    assert get_args(hint) == (int, Min(value=0), Max(value=100), Min(value=10))


def test_flatten_order_is_deterministic():
    def build():
        return get_args(Annotated[Annotated[int, Min(value=1), Max(value=9)], Min(value=3)])

    assert build() == build()
    assert build() == (int, Min(value=1), Max(value=9), Min(value=3))


def test_alias_extension_outer_wins():
    Percent: TypeAlias = Annotated[int, Min(value=0), Max(value=100)]

    @dataclass
    class C:
        pct: Annotated[Percent, Max(value=50)] = 25

    (f,) = struct_of(C).fields
    shape = f.shape[0]
    assert shape.max == Max(value=50)
    assert shape.min == Min(value=0)


def test_alias_extension_can_relax_too():
    Small: TypeAlias = Annotated[int, Min(value=0), Max(value=10)]

    @dataclass
    class C:
        n: Annotated[Small, Max(value=100)] = 50

    shape = struct_of(C).fields[0].shape[0]
    assert shape.max == Max(value=100)
    assert shape.min == Min(value=0)


def test_field_atom_also_composes():
    Base: TypeAlias = Annotated[int, Min(value=0), Label(value="base")]

    @dataclass
    class C:
        n: Annotated[Base, Label(value="outer")] = 0

    (f,) = struct_of(C).fields
    assert f.label == Label(value="outer")
    assert f.shape[0].min == Min(value=0)


def test_composition_across_three_layers():
    Base: TypeAlias = Annotated[int, Min(value=0), Max(value=100)]
    Mid: TypeAlias = Annotated[Base, Max(value=80)]

    @dataclass
    class C:
        n: Annotated[Mid, Max(value=50), Slider()] = 10

    shape = struct_of(C).fields[0].shape[0]
    assert shape.min == Min(value=0)
    assert shape.max == Max(value=50)
    assert shape.slider == Slider()


def test_outermost_of_many_repeats_wins():
    A: TypeAlias = Annotated[int, Max(value=1)]
    B: TypeAlias = Annotated[A, Max(value=2)]
    D: TypeAlias = Annotated[B, Max(value=3)]

    @dataclass
    class C:
        n: Annotated[D, Max(value=4)] = 0

    assert struct_of(C).fields[0].shape[0].max == Max(value=4)


def test_distinct_atoms_are_order_independent():
    @dataclass
    class A:
        n: Annotated[int, Min(value=0), Max(value=9), Label(value="N")] = 4

    @dataclass
    class B:
        n: Annotated[int, Label(value="N"), Max(value=9), Min(value=0)] = 4

    assert repr(struct_of(A).fields[0]) == repr(struct_of(B).fields[0])


def test_same_atom_is_order_dependent():
    @dataclass
    class A:
        n: Annotated[int, Max(value=10), Max(value=100)] = 5

    @dataclass
    class B:
        n: Annotated[int, Max(value=100), Max(value=10)] = 5

    assert struct_of(A).fields[0].shape[0].max == Max(value=100)
    assert struct_of(B).fields[0].shape[0].max == Max(value=10)


def test_composition_is_reproducible():
    Percent: TypeAlias = Annotated[int, Min(value=0), Max(value=100)]

    @dataclass
    class C:
        pct: Annotated[Percent, Max(value=50), Label(value="Pct")] = 25

    assert repr(struct_of(C).fields) == repr(struct_of(C).fields)


def test_deep_stack_composes_every_dimension():
    Percent: TypeAlias = Annotated[int, Min(value=0), Max(value=100)]

    @dataclass
    class C:
        volume: Annotated[
            Annotated[Percent, Max(value=80)],
            Slider(), Label(value="Vol"), Description(value="0 a 80"),
        ] = 60

    (f,) = struct_of(C).fields
    assert f.shape[0] == Int(min=Min(value=0), max=Max(value=80), slider=Slider())
    assert f.label == Label(value="Vol")
    assert f.description == Description(value="0 a 80")
    assert f.default == 60


def test_composition_inside_a_list_item():
    Percent: TypeAlias = Annotated[int, Min(value=0), Max(value=100)]

    @dataclass
    class C:
        ns: list[Annotated[Percent, Max(value=10)]] = field(default_factory=list)

    shape = struct_of(C).fields[0].shape[0]
    assert shape == List(item=(Int(min=Min(value=0), max=Max(value=10)),))


def test_override_that_invalidates_default_is_caught():
    Percent: TypeAlias = Annotated[int, Min(value=0), Max(value=100)]

    @dataclass
    class C:
        pct: Annotated[Percent, Max(value=10)] = 50

    with pytest.raises(ValueError, match="too large"):
        struct_of(C)


def test_override_can_create_empty_range():
    AtLeastTen: TypeAlias = Annotated[int, Min(value=10)]

    @dataclass
    class C:
        n: Annotated[AtLeastTen, Max(value=1)] = 10

    with pytest.raises(ValueError, match="empty range"):
        struct_of(C)


def test_layered_override_replaces_inclusive_with_exclusive():
    Base: TypeAlias = Annotated[int, Min(value=0)]

    @dataclass
    class C:
        n: Annotated[Base, Min(value=0, exclusive=True)] = 1

    shape = struct_of(C).fields[0].shape[0]
    assert shape.min == Min(value=0, exclusive=True)
    assert shape.min.exclusive is True

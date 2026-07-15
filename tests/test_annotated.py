from dataclasses import dataclass, field
from typing import Annotated, Optional, TypeAlias, Union, get_args, get_origin

import pytest

from pytypehint.atoms import (
    Choices, Description, Label, Max, Min, Placeholder, Slider, Step,
)
from pytypehint.bridge import struct_of
from pytypehint.shapes import Bool, Int, List, NoneShape
from pytypehint.structure import Field, Struct


def case_type_atom_on_bare_type():
    @dataclass
    class C:
        n: Annotated[int, Min(value=0)]

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(min=Min(value=0)),)),
    ))


def case_field_atom_on_bare_type():
    @dataclass
    class C:
        n: Annotated[int, Label(value="N")]

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(),), label=Label(value="N")),
    ))


def case_both_kinds_interleaved():
    @dataclass
    class C:
        n: Annotated[
            int, Label(value="N"), Min(value=0), Description(value="d"), Max(value=9)
        ] = 4

    return C, Struct(cls=C, fields=(
        Field(
            name="n",
            shape=(Int(min=Min(value=0), max=Max(value=9)),),
            default=4,
            label=Label(value="N"),
            description=Description(value="d"),
        ),
    ))


def case_atom_order_reversed_same_result():
    @dataclass
    class C:
        n: Annotated[
            int, Max(value=9), Description(value="d"), Min(value=0), Label(value="N")
        ] = 4

    return C, Struct(cls=C, fields=(
        Field(
            name="n",
            shape=(Int(min=Min(value=0), max=Max(value=9)),),
            default=4,
            label=Label(value="N"),
            description=Description(value="d"),
        ),
    ))


def case_nested_annotated_flattens():
    @dataclass
    class C:
        n: Annotated[Annotated[int, Min(value=0)], Max(value=10)] = 5

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(min=Min(value=0), max=Max(value=10)),), default=5),
    ))


def case_nested_annotated_three_deep():
    @dataclass
    class C:
        n: Annotated[
            Annotated[Annotated[int, Min(value=0)], Max(value=10)],
            Label(value="N"),
        ] = 5

    return C, Struct(cls=C, fields=(
        Field(
            name="n",
            shape=(Int(min=Min(value=0), max=Max(value=10)),),
            default=5,
            label=Label(value="N"),
        ),
    ))


def case_alias_reused_and_extended():
    Percent: TypeAlias = Annotated[int, Min(value=0), Max(value=100)]

    @dataclass
    class C:
        volume: Annotated[Percent, Slider(), Label(value="Vol")] = 50

    return C, Struct(cls=C, fields=(
        Field(
            name="volume",
            shape=(Int(min=Min(value=0), max=Max(value=100), slider=Slider()),),
            default=50,
            label=Label(value="Vol"),
        ),
    ))


def case_alias_atom_overridden_last_wins():
    Small: TypeAlias = Annotated[int, Max(value=10)]

    @dataclass
    class C:
        n: Annotated[Small, Max(value=100)] = 50

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(max=Max(value=100)),), default=50),
    ))


def case_alias_atom_overridden_tightening():
    Big: TypeAlias = Annotated[int, Max(value=100)]

    @dataclass
    class C:
        n: Annotated[Big, Max(value=10)] = 5

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(max=Max(value=10)),), default=5),
    ))


def case_repeated_atom_direct():
    @dataclass
    class C:
        n: Annotated[int, Min(value=1), Min(value=3)]

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(min=Min(value=3)),)),
    ))


def case_repeated_field_atom_last_wins():
    @dataclass
    class C:
        n: Annotated[int, Label(value="A"), Label(value="B")]

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(),), label=Label(value="B")),
    ))


def case_type_atoms_inside_option():
    @dataclass
    class C:
        n: Annotated[int, Min(value=0)] | None = None

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(min=Min(value=0)), NoneShape()), default=None),
    ))


def case_field_atoms_over_union():
    @dataclass
    class C:
        n: Annotated[int | None, Label(value="N")] = None

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(), NoneShape()), default=None, label=Label(value="N")),
    ))


def case_field_atoms_over_union_type_atoms_inside():
    @dataclass
    class C:
        n: Annotated[
            Annotated[int, Min(value=1), Max(value=10)] | None,
            Label(value="N"), Description(value="1 a 10, o nada"),
        ] = None

    return C, Struct(cls=C, fields=(
        Field(
            name="n",
            shape=(Int(min=Min(value=1), max=Max(value=10)), NoneShape()),
            default=None,
            label=Label(value="N"),
            description=Description(value="1 a 10, o nada"),
        ),
    ))


def case_atoms_on_both_options():
    @dataclass
    class C:
        n: Annotated[int, Min(value=0)] | Annotated[bool, ...] if False else int

    raise AssertionError("unused")


def case_atoms_on_int_option_bool_bare():
    @dataclass
    class C:
        n: Annotated[int, Min(value=0)] | bool = True

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(min=Min(value=0)), Bool()), default=True),
    ))


def case_alias_inside_union():
    Percent: TypeAlias = Annotated[int, Min(value=0), Max(value=100)]

    @dataclass
    class C:
        volume: Percent | None = None

    return C, Struct(cls=C, fields=(
        Field(
            name="volume",
            shape=(Int(min=Min(value=0), max=Max(value=100)), NoneShape()),
            default=None,
        ),
    ))


def case_optional_alias_with_label_outside():
    Percent: TypeAlias = Annotated[int, Min(value=0), Max(value=100)]

    @dataclass
    class C:
        volume: Annotated[Percent | None, Label(value="Vol")] = None

    return C, Struct(cls=C, fields=(
        Field(
            name="volume",
            shape=(Int(min=Min(value=0), max=Max(value=100)), NoneShape()),
            default=None,
            label=Label(value="Vol"),
        ),
    ))


def case_typing_optional_with_annotated_inside():
    @dataclass
    class C:
        n: Optional[Annotated[int, Min(value=0)]] = None

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(min=Min(value=0)), NoneShape()), default=None),
    ))


def case_typing_union_with_annotated_inside():
    @dataclass
    class C:
        n: Union[Annotated[int, Min(value=0)], None] = None

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(min=Min(value=0)), NoneShape()), default=None),
    ))


def case_annotated_on_list_bounds_length():
    @dataclass
    class C:
        ns: Annotated[list[int], Min(value=1), Max(value=3)] = field(
            default_factory=lambda: [1]
        )

    return C, Struct(cls=C, fields=(
        Field(
            name="ns",
            shape=(List(item=(Int(),), min=Min(value=1), max=Max(value=3)),),
            default=[1],
        ),
    ))


def case_annotated_on_item_bounds_value():
    @dataclass
    class C:
        ns: list[Annotated[int, Min(value=0), Max(value=9)]] = field(default_factory=list)

    return C, Struct(cls=C, fields=(
        Field(
            name="ns",
            shape=(List(item=(Int(min=Min(value=0), max=Max(value=9)),)),),
            default=[],
        ),
    ))


def case_annotated_on_both_list_and_item():
    @dataclass
    class C:
        ns: Annotated[
            list[Annotated[int, Min(value=0), Max(value=9)]],
            Min(value=1), Max(value=3),
        ] = field(default_factory=lambda: [5])

    return C, Struct(cls=C, fields=(
        Field(
            name="ns",
            shape=(List(
                item=(Int(min=Min(value=0), max=Max(value=9)),),
                min=Min(value=1), max=Max(value=3),
            ),),
            default=[5],
        ),
    ))


def case_annotated_on_list_and_field_atoms_outside():
    @dataclass
    class C:
        ns: Annotated[
            list[Annotated[int, Min(value=0)]],
            Min(value=1), Label(value="Ns"), Description(value="al menos uno"),
        ] = field(default_factory=lambda: [0])

    return C, Struct(cls=C, fields=(
        Field(
            name="ns",
            shape=(List(item=(Int(min=Min(value=0)),), min=Min(value=1)),),
            default=[0],
            label=Label(value="Ns"),
            description=Description(value="al menos uno"),
        ),
    ))


def case_annotated_nested_lists_each_layer():
    @dataclass
    class C:
        grid: Annotated[
            list[Annotated[list[Annotated[int, Max(value=9)]], Max(value=2)]],
            Max(value=4),
        ] = field(default_factory=list)

    return C, Struct(cls=C, fields=(
        Field(
            name="grid",
            shape=(List(
                item=(List(item=(Int(max=Max(value=9)),), max=Max(value=2)),),
                max=Max(value=4),
            ),),
            default=[],
        ),
    ))


SCHEMA_CASES = [
    case_type_atom_on_bare_type,
    case_field_atom_on_bare_type,
    case_both_kinds_interleaved,
    case_atom_order_reversed_same_result,
    case_nested_annotated_flattens,
    case_nested_annotated_three_deep,
    case_alias_reused_and_extended,
    case_alias_atom_overridden_last_wins,
    case_alias_atom_overridden_tightening,
    case_repeated_atom_direct,
    case_repeated_field_atom_last_wins,
    case_type_atoms_inside_option,
    case_field_atoms_over_union,
    case_field_atoms_over_union_type_atoms_inside,
    case_atoms_on_int_option_bool_bare,
    case_alias_inside_union,
    case_optional_alias_with_label_outside,
    case_typing_optional_with_annotated_inside,
    case_typing_union_with_annotated_inside,
    case_annotated_on_list_bounds_length,
    case_annotated_on_item_bounds_value,
    case_annotated_on_both_list_and_item,
    case_annotated_on_list_and_field_atoms_outside,
    case_annotated_nested_lists_each_layer,
]


@pytest.mark.parametrize("case", SCHEMA_CASES, ids=lambda c: c.__name__.removeprefix("case_"))
def test_schema(case):
    cls, expected = case()
    assert repr(struct_of(cls).fields) == repr(expected.fields)


def test_alias_is_not_mutated_by_extension():
    Percent: TypeAlias = Annotated[int, Min(value=0), Max(value=100)]

    @dataclass
    class A:
        n: Annotated[Percent, Slider()] = 50

    @dataclass
    class B:
        n: Percent = 50

    (fa,) = struct_of(A).fields
    (fb,) = struct_of(B).fields
    assert fa.shape[0].slider == Slider()
    assert fb.shape[0].slider is None


def reject_slider_over_union():
    @dataclass
    class C:
        n: Annotated[int | None, Slider()] = None

    return C


def reject_type_atom_over_union_of_two_types():
    @dataclass
    class C:
        n: Annotated[int | bool, Min(value=0)] = 0

    return C


def reject_slider_on_bool():
    @dataclass
    class C:
        b: Annotated[bool, Slider()] = False

    return C


def reject_min_on_bool_option():
    @dataclass
    class C:
        b: Annotated[bool, Min(value=0)] | None = None

    return C


def reject_slider_on_none_option():
    @dataclass
    class C:
        n: int | Annotated[None, Slider()] = None

    return C


def reject_step_on_list():
    @dataclass
    class C:
        ns: Annotated[list[int], Step(value=2)] = field(default_factory=list)

    return C


def reject_label_on_list_item():
    @dataclass
    class C:
        ns: list[Annotated[int, Label(value="X")]] = field(default_factory=list)

    return C


def reject_class_as_metadata():
    @dataclass
    class C:
        n: Annotated[int, Min]

    return C


def reject_string_as_metadata():
    @dataclass
    class C:
        n: Annotated[int, "algo de otra librería"] = 0

    return C


def reject_alias_override_invalidates_default():
    Big: TypeAlias = Annotated[int, Max(value=100)]

    @dataclass
    class C:
        n: Annotated[Big, Max(value=10)] = 50

    return C


def reject_flattened_atoms_make_empty_range():
    AtLeastTen: TypeAlias = Annotated[int, Min(value=10)]

    @dataclass
    class C:
        n: Annotated[AtLeastTen, Max(value=1)] = 10

    return C


def reject_flattened_slider_without_bounds():
    @dataclass
    class C:
        n: Annotated[Annotated[int, Label(value="N")], Slider()] = 0

    return C


REJECT_CASES = [
    (reject_slider_over_union, ValueError, "slider requires min and max"),
    (reject_type_atom_over_union_of_two_types, TypeError, "must go per option"),
    (reject_slider_on_bool, TypeError, "unsupported metadata for bool"),
    (reject_min_on_bool_option, TypeError, "unsupported metadata for bool"),
    (reject_slider_on_none_option, TypeError, "unsupported metadata for None"),
    (reject_step_on_list, TypeError, "unsupported metadata for list"),
    (reject_label_on_list_item, TypeError, "field atoms cannot apply to list items"),
    (reject_class_as_metadata, TypeError, "unsupported metadata for int"),
    (reject_string_as_metadata, TypeError, "unsupported metadata for int"),
    (reject_alias_override_invalidates_default, ValueError, "too large"),
    (reject_flattened_atoms_make_empty_range, ValueError, "empty range"),
    (reject_flattened_slider_without_bounds, ValueError, "slider requires min and max"),
]


@pytest.mark.parametrize(
    "case, exc, match", REJECT_CASES,
    ids=[c.__name__.removeprefix("reject_") for c, _, _ in REJECT_CASES],
)
def test_schema_rejected(case, exc, match):
    with pytest.raises(exc, match=match):
        struct_of(case())


def test_annotated_takes_one_type_plus_metadata():

    hint = Annotated[int, Min(value=0), Label(value="N")]
    assert get_origin(hint) is Annotated
    base, *meta = get_args(hint)
    assert base is int
    assert meta == [Min(value=0), Label(value="N")]


def test_annotated_flattening_is_typings_doing():

    inner = Annotated[int, Min(value=0)]
    outer = Annotated[inner, Max(value=10)]
    assert get_args(outer) == (int, Min(value=0), Max(value=10))


def test_union_stops_the_flattening():

    hint = Annotated[Annotated[int, Min(value=1)] | None, Label(value="N")]
    base, *meta = get_args(hint)
    assert meta == [Label(value="N")]
    assert get_origin(base) is not Annotated

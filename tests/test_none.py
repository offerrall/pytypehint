from dataclasses import dataclass, field
from typing import Annotated, Optional, Union

import pytest

from pytypehint.atoms import Choices, Description, Label, Max, Min, Slider, Step
from pytypehint.bridge import struct_of
from pytypehint.shapes import Bool, Int, List, NoneShape
from pytypehint.structure import Field, Struct
from pytypehint.utils import MISSING


def case_optional_int():
    @dataclass
    class C:
        n: int | None = None

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(), NoneShape()), default=None),
    ))


def case_optional_int_no_default():
    @dataclass
    class C:
        n: int | None

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(), NoneShape())),
    ))


def case_optional_int_default_is_int():
    @dataclass
    class C:
        n: int | None = 7

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(), NoneShape()), default=7),
    ))


def case_optional_bool():
    @dataclass
    class C:
        active: bool | None = None

    return C, Struct(cls=C, fields=(
        Field(name="active", shape=(Bool(), NoneShape()), default=None),
    ))


def case_typing_optional():
    @dataclass
    class C:
        n: Optional[int] = None

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(), NoneShape()), default=None),
    ))


def case_typing_union():
    @dataclass
    class C:
        n: Union[int, None] = None

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(), NoneShape()), default=None),
    ))


def case_none_first_preserves_order():
    @dataclass
    class C:
        n: Union[None, int] = None

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(NoneShape(), Int()), default=None),
    ))


def case_three_options():
    @dataclass
    class C:
        n: int | bool | None = None

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(), Bool(), NoneShape()), default=None),
    ))


def case_type_atoms_inside_option():
    @dataclass
    class C:
        n: Annotated[int, Min(value=0)] | None = None

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(min=Min(value=0)), NoneShape()), default=None),
    ))


def case_many_type_atoms_inside_option():
    @dataclass
    class C:
        n: Annotated[int, Min(value=0), Max(value=100), Slider(), Step(value=5)] | None = None

    return C, Struct(cls=C, fields=(
        Field(
            name="n",
            shape=(
                Int(min=Min(value=0), max=Max(value=100), slider=Slider(), step=Step(value=5)),
                NoneShape(),
            ),
            default=None,
        ),
    ))


def case_field_atoms_outside_union():
    @dataclass
    class C:
        n: Annotated[int | None, Label(value="N")] = None

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(), NoneShape()), default=None, label=Label(value="N")),
    ))


def case_field_atoms_outside_union_full():
    @dataclass
    class C:
        n: Annotated[int | None, Label(value="N"), Description(value="Opcional")] = None

    return C, Struct(cls=C, fields=(
        Field(
            name="n",
            shape=(Int(), NoneShape()),
            default=None,
            label=Label(value="N"),
            description=Description(value="Opcional"),
        ),
    ))


def case_atoms_both_layers():
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


def case_atoms_both_layers_with_choices():
    @dataclass
    class C:
        n: Annotated[
            Annotated[int, Choices(values=(1, 2, 3))] | None,
            Label(value="N"),
        ] = 2

    return C, Struct(cls=C, fields=(
        Field(
            name="n",
            shape=(Int(choices=Choices(values=(1, 2, 3))), NoneShape()),
            default=2,
            label=Label(value="N"),
        ),
    ))


def case_optional_list():
    @dataclass
    class C:
        ns: list[int] | None = None

    return C, Struct(cls=C, fields=(
        Field(name="ns", shape=(List(item=(Int(),)), NoneShape()), default=None),
    ))


def case_optional_list_with_bounds():
    @dataclass
    class C:
        ns: Annotated[list[int], Min(value=1), Max(value=3)] | None = None

    return C, Struct(cls=C, fields=(
        Field(
            name="ns",
            shape=(List(item=(Int(),), min=Min(value=1), max=Max(value=3)), NoneShape()),
            default=None,
        ),
    ))


def case_optional_list_of_constrained_items():
    @dataclass
    class C:
        ns: list[Annotated[int, Min(value=0)]] | None = None

    return C, Struct(cls=C, fields=(
        Field(
            name="ns",
            shape=(List(item=(Int(min=Min(value=0)),)), NoneShape()),
            default=None,
        ),
    ))


def case_optional_dataclass():
    @dataclass
    class Inner:
        n: int = 0

    @dataclass
    class Outer:
        inner: Inner | None = None

    return Outer, Struct(cls=Outer, fields=(
        Field(
            name="inner",
            shape=(
                Struct(cls=Inner, fields=(Field(name="n", shape=(Int(),), default=0),)),
                NoneShape(),
            ),
            default=None,
        ),
    ))


def case_optional_inside_nested_dataclass():
    @dataclass
    class Inner:
        n: Annotated[int, Min(value=0)] | None = None

    @dataclass
    class Outer:
        inner: Inner = field(default_factory=Inner)

    return Outer, Struct(cls=Outer, fields=(
        Field(
            name="inner",
            shape=(Struct(cls=Inner, fields=(
                Field(name="n", shape=(Int(min=Min(value=0)), NoneShape()), default=None),
            )),),
            default=Inner(),
        ),
    ))


def case_multiple_optional_fields():
    @dataclass
    class C:
        a: int | None
        b: Annotated[int, Min(value=0)] | None = None
        c: Annotated[bool | None, Label(value="C")] = None
        d: list[int] | None = None

    return C, Struct(cls=C, fields=(
        Field(name="a", shape=(Int(), NoneShape())),
        Field(name="b", shape=(Int(min=Min(value=0)), NoneShape()), default=None),
        Field(name="c", shape=(Bool(), NoneShape()), default=None, label=Label(value="C")),
        Field(name="d", shape=(List(item=(Int(),)), NoneShape()), default=None),
    ))


SCHEMA_CASES = [
    case_optional_int,
    case_optional_int_no_default,
    case_optional_int_default_is_int,
    case_optional_bool,
    case_typing_optional,
    case_typing_union,
    case_none_first_preserves_order,
    case_three_options,
    case_type_atoms_inside_option,
    case_many_type_atoms_inside_option,
    case_field_atoms_outside_union,
    case_field_atoms_outside_union_full,
    case_atoms_both_layers,
    case_atoms_both_layers_with_choices,
    case_optional_list,
    case_optional_list_with_bounds,
    case_optional_list_of_constrained_items,
    case_optional_dataclass,
    case_optional_inside_nested_dataclass,
    case_multiple_optional_fields,
]


@pytest.mark.parametrize("case", SCHEMA_CASES, ids=lambda c: c.__name__.removeprefix("case_"))
def test_schema(case):
    cls, expected = case()
    assert repr(struct_of(cls).fields) == repr(expected.fields)


def test_optional_int_default_none_is_none_not_falsy():
    @dataclass
    class C:
        n: int | None = None

    (f,) = struct_of(C).fields
    assert f.default is None


def reject_bare_none():
    @dataclass
    class C:
        nothing: None = None

    return C


def reject_bare_none_no_default():
    @dataclass
    class C:
        nothing: None

    return C


def reject_annotated_none_alone():
    @dataclass
    class C:
        nothing: Annotated[None, Label(value="Nada")] = None

    return C


def reject_list_of_none():
    @dataclass
    class C:
        holes: list[None] = field(default_factory=list)

    return C


def reject_list_of_list_of_none():
    @dataclass
    class C:
        grid: list[list[None]] = field(default_factory=list)

    return C


def reject_optional_list_of_none():
    @dataclass
    class C:
        holes: list[None] | None = None

    return C


def reject_type_metadata_on_none_option():
    @dataclass
    class C:
        n: int | Annotated[None, Slider()] = None

    return C


def reject_union_as_list_item():
    @dataclass
    class C:
        ns: list[int | None] = field(default_factory=list)

    return C


def reject_bool_default_on_optional_int():
    @dataclass
    class C:
        n: int | None = True

    return C


def reject_str_default_on_optional_int():
    @dataclass
    class C:
        n: int | None = "x"

    return C


def reject_none_default_outside_constraint():
    @dataclass
    class C:
        n: Annotated[int, Min(value=10)] | None = 5

    return C


REJECT_CASES = [
    (reject_bare_none, TypeError, "must be accompanied"),
    (reject_bare_none_no_default, TypeError, "must be accompanied"),
    (reject_annotated_none_alone, TypeError, "must be accompanied"),
    (reject_list_of_none, TypeError, "cannot be NoneShape"),
    (reject_list_of_list_of_none, TypeError, "cannot be NoneShape"),
    (reject_optional_list_of_none, TypeError, "cannot be NoneShape"),
    (reject_type_metadata_on_none_option, TypeError, "unsupported metadata for None"),
    (reject_bool_default_on_optional_int, TypeError, "expected int"),
    (reject_str_default_on_optional_int, TypeError, "expected int"),
    (reject_none_default_outside_constraint, ValueError, "too small"),
]


@pytest.mark.parametrize(
    "case, exc, match", REJECT_CASES,
    ids=[c.__name__.removeprefix("reject_") for c, _, _ in REJECT_CASES],
)
def test_schema_rejected(case, exc, match):
    with pytest.raises(exc, match=match):
        struct_of(case())


def test_field_rejects_lone_noneshape():
    with pytest.raises(TypeError, match="must be accompanied"):
        Field(name="x", shape=(NoneShape(),))


def test_list_rejects_noneshape_item():
    with pytest.raises(TypeError, match="List.item cannot be NoneShape"):
        List(item=(NoneShape(),))


def test_field_accepts_noneshape_with_company():
    Field(name="x", shape=(Int(), NoneShape()), default=None)
    Field(name="x", shape=(NoneShape(), Int()), default=None)


def test_dispatch_picks_the_right_option():
    f = Field(name="n", shape=(Int(min=Min(value=0)), NoneShape()), default=None)
    f._check_value(None)
    f._check_value(0)

    with pytest.raises(ValueError, match="too small"):
        f._check_value(-1)

    with pytest.raises(TypeError, match="expected int"):
        f._check_value("x")


def test_noneshape_check_rejects_falsy_values():
    for value in (0, False, "", []):
        with pytest.raises(TypeError, match="expected None"):
            NoneShape()._check(value)


def test_struct_check_on_instances():
    @dataclass
    class C:
        n: Annotated[int, Min(value=0)] | None = None

    s = struct_of(C)
    s._check(C())
    s._check(C(n=5))

    with pytest.raises(ValueError, match="too small"):
        s._check(C(n=-1))

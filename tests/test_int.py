from dataclasses import dataclass, field
from typing import Annotated

import pytest

from pytypehint.atoms import (
    Choices, Description, Label, Max, Min, MultipleOf, Placeholder, Slider, Step,
)
from pytypehint.bridge import struct_of
from pytypehint.shapes import Bool, Int, List, NoneShape
from pytypehint.structure import Field, Struct
from pytypehint.utils import MISSING


def case_bare_int():
    @dataclass
    class C:
        n: int

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(),)),
    ))


def case_int_default_zero():
    @dataclass
    class C:
        n: int = 0

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(),), default=0),
    ))


def case_int_default_negative():
    @dataclass
    class C:
        n: int = -42

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(),), default=-42),
    ))


def case_int_min():
    @dataclass
    class C:
        n: Annotated[int, Min(value=0)]

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(min=Min(value=0)),)),
    ))


def case_int_max():
    @dataclass
    class C:
        n: Annotated[int, Max(value=100)]

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(max=Max(value=100)),)),
    ))


def case_int_min_max():
    @dataclass
    class C:
        n: Annotated[int, Min(value=1), Max(value=10)]

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(min=Min(value=1), max=Max(value=10)),)),
    ))


def case_int_min_equals_max():
    @dataclass
    class C:
        n: Annotated[int, Min(value=5), Max(value=5)]

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(min=Min(value=5), max=Max(value=5)),)),
    ))


def case_int_choices():
    @dataclass
    class C:
        n: Annotated[int, Choices(values=(1, 2, 3))]

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(choices=Choices(values=(1, 2, 3))),)),
    ))


def case_int_choices_within_range():
    @dataclass
    class C:
        n: Annotated[int, Min(value=0), Max(value=10), Choices(values=(0, 5, 10))]

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(
            Int(min=Min(value=0), max=Max(value=10), choices=Choices(values=(0, 5, 10))),
        )),
    ))


def case_int_step():
    @dataclass
    class C:
        n: Annotated[int, Step(value=5)]

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(step=Step(value=5)),)),
    ))


def case_int_slider():
    @dataclass
    class C:
        n: Annotated[int, Min(value=0), Max(value=100), Slider()]

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(
            Int(min=Min(value=0), max=Max(value=100), slider=Slider()),
        )),
    ))


def case_int_slider_hidden_value():
    @dataclass
    class C:
        n: Annotated[int, Min(value=0), Max(value=10), Slider(show_value=False)]

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(
            Int(min=Min(value=0), max=Max(value=10), slider=Slider(show_value=False)),
        )),
    ))


def case_int_placeholder():
    @dataclass
    class C:
        n: Annotated[int, Placeholder(value="Enter a number")]

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(placeholder=Placeholder(value="Enter a number")),)),
    ))


def case_int_all_atoms():
    @dataclass
    class C:
        n: Annotated[
            int,
            Min(value=0), Max(value=100), Choices(values=(0, 10, 50, 100)),
            Step(value=10), Slider(), Placeholder(value="pick"),
            Label(value="Amount"), Description(value="How many"),
        ] = 50

    return C, Struct(cls=C, fields=(
        Field(
            name="n",
            shape=(Int(
                min=Min(value=0), max=Max(value=100),
                choices=Choices(values=(0, 10, 50, 100)),
                step=Step(value=10), slider=Slider(),
                placeholder=Placeholder(value="pick"),
            ),),
            default=50,
            label=Label(value="Amount"),
            description=Description(value="How many"),
        ),
    ))


def case_int_repeated_atom_last_wins():
    @dataclass
    class C:
        n: Annotated[int, Min(value=1), Min(value=3)]

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(min=Min(value=3)),)),
    ))


def case_int_label():
    @dataclass
    class C:
        n: Annotated[int, Label(value="Count")]

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(),), label=Label(value="Count")),
    ))


def case_int_label_description_and_type_atoms_mixed():
    @dataclass
    class C:
        n: Annotated[int, Label(value="Count"), Min(value=0), Description(value="d"), Max(value=9)]

    return C, Struct(cls=C, fields=(
        Field(
            name="n",
            shape=(Int(min=Min(value=0), max=Max(value=9)),),
            label=Label(value="Count"),
            description=Description(value="d"),
        ),
    ))


def case_optional_int():
    @dataclass
    class C:
        n: int | None = None

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(), NoneShape()), default=None),
    ))


def case_optional_int_default_int():
    @dataclass
    class C:
        n: int | None = 7

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(), NoneShape()), default=7),
    ))


def case_union_int_bool():
    @dataclass
    class C:
        n: int | bool

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(), Bool())),
    ))


def case_union_per_option_metadata():
    @dataclass
    class C:
        n: Annotated[int, Min(value=0)] | None = None

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(min=Min(value=0)), NoneShape()), default=None),
    ))


def case_union_per_option_metadata_with_field_atoms_outside():
    @dataclass
    class C:
        n: Annotated[Annotated[int, Min(value=1)] | None, Label(value="N")] = None

    return C, Struct(cls=C, fields=(
        Field(
            name="n",
            shape=(Int(min=Min(value=1)), NoneShape()),
            default=None,
            label=Label(value="N"),
        ),
    ))


def case_single_type_metadata_via_field_level_annotated():
    @dataclass
    class C:
        n: Annotated[int, Label(value="N"), Min(value=2)]

    return C, Struct(cls=C, fields=(
        Field(name="n", shape=(Int(min=Min(value=2)),), label=Label(value="N")),
    ))


def case_list_of_int():
    @dataclass
    class C:
        ns: list[int] = field(default_factory=list)

    return C, Struct(cls=C, fields=(
        Field(name="ns", shape=(List(item=(Int(),)),), default=[]),
    ))


def case_list_of_int_with_length_bounds():
    @dataclass
    class C:
        ns: Annotated[list[int], Min(value=1), Max(value=5)] = field(default_factory=lambda: [1])

    return C, Struct(cls=C, fields=(
        Field(
            name="ns",
            shape=(List(item=(Int(),), min=Min(value=1), max=Max(value=5)),),
            default=[1],
        ),
    ))


def case_list_of_constrained_int():
    @dataclass
    class C:
        ns: list[Annotated[int, Min(value=0), Max(value=10)]] = field(default_factory=list)

    return C, Struct(cls=C, fields=(
        Field(
            name="ns",
            shape=(List(item=(Int(min=Min(value=0), max=Max(value=10)),)),),
            default=[],
        ),
    ))


def case_list_of_list_of_int():
    @dataclass
    class C:
        grid: list[list[int]] = field(default_factory=list)

    return C, Struct(cls=C, fields=(
        Field(name="grid", shape=(List(item=(List(item=(Int(),)),)),), default=[]),
    ))


def case_optional_list_of_int():
    @dataclass
    class C:
        ns: list[int] | None = None

    return C, Struct(cls=C, fields=(
        Field(name="ns", shape=(List(item=(Int(),)), NoneShape()), default=None),
    ))


def case_nested_dataclass_with_int():
    @dataclass
    class Inner:
        n: Annotated[int, Min(value=0)] = 0

    @dataclass
    class Outer:
        inner: Inner = field(default_factory=Inner)

    return Outer, Struct(cls=Outer, fields=(
        Field(
            name="inner",
            shape=(Struct(cls=Inner, fields=(
                Field(name="n", shape=(Int(min=Min(value=0)),), default=0),
            )),),
            default=Inner(),
        ),
    ))


def case_multiple_int_fields():
    @dataclass
    class C:
        a: int
        b: Annotated[int, Min(value=0)] = 0
        c: int | None = None
        d: Annotated[int, Choices(values=(1, 2))] = 2

    return C, Struct(cls=C, fields=(
        Field(name="a", shape=(Int(),)),
        Field(name="b", shape=(Int(min=Min(value=0)),), default=0),
        Field(name="c", shape=(Int(), NoneShape()), default=None),
        Field(name="d", shape=(Int(choices=Choices(values=(1, 2))),), default=2),
    ))


SCHEMA_CASES = [
    case_bare_int,
    case_int_default_zero,
    case_int_default_negative,
    case_int_min,
    case_int_max,
    case_int_min_max,
    case_int_min_equals_max,
    case_int_choices,
    case_int_choices_within_range,
    case_int_step,
    case_int_slider,
    case_int_slider_hidden_value,
    case_int_placeholder,
    case_int_all_atoms,
    case_int_repeated_atom_last_wins,
    case_int_label,
    case_int_label_description_and_type_atoms_mixed,
    case_optional_int,
    case_optional_int_default_int,
    case_union_int_bool,
    case_union_per_option_metadata,
    case_union_per_option_metadata_with_field_atoms_outside,
    case_single_type_metadata_via_field_level_annotated,
    case_list_of_int,
    case_list_of_int_with_length_bounds,
    case_list_of_constrained_int,
    case_list_of_list_of_int,
    case_optional_list_of_int,
    case_nested_dataclass_with_int,
    case_multiple_int_fields,
]


@pytest.mark.parametrize("case", SCHEMA_CASES, ids=lambda c: c.__name__.removeprefix("case_"))
def test_schema(case):
    cls, expected = case()
    result = struct_of(cls)
    assert repr(result.fields) == repr(expected.fields)
    for got, exp in zip(result.fields, expected.fields):
        if exp.default is not MISSING:
            assert type(got.default) is type(exp.default)


def reject_slider_without_bounds():
    @dataclass
    class C:
        n: Annotated[int, Slider()]

    return C


def reject_slider_with_only_min():
    @dataclass
    class C:
        n: Annotated[int, Min(value=0), Slider()]

    return C


def reject_empty_range():
    @dataclass
    class C:
        n: Annotated[int, Min(value=10), Max(value=1)]

    return C


def reject_choice_below_min():
    @dataclass
    class C:
        n: Annotated[int, Min(value=5), Choices(values=(1, 6))]

    return C


def reject_choice_above_max():
    @dataclass
    class C:
        n: Annotated[int, Max(value=5), Choices(values=(1, 6))]

    return C


def reject_unknown_metadata_for_int():
    @dataclass
    class C:
        n: Annotated[int, Label]

    return C


def reject_default_below_min():
    @dataclass
    class C:
        n: Annotated[int, Min(value=10)] = 5

    return C


def reject_default_above_max():
    @dataclass
    class C:
        n: Annotated[int, Max(value=10)] = 50

    return C


def reject_default_not_in_choices():
    @dataclass
    class C:
        n: Annotated[int, Choices(values=(1, 2, 3))] = 9

    return C


def reject_bool_default_on_int_field():
    @dataclass
    class C:
        n: int = True

    return C


def reject_str_default_on_int_field():
    @dataclass
    class C:
        n: int = "7"

    return C


def reject_none_default_without_none_option():
    @dataclass
    class C:
        n: int = None

    return C


def reject_union_of_list_items():
    @dataclass
    class C:
        ns: list[int | None] = field(default_factory=list)

    return C


def reject_bare_list():
    @dataclass
    class C:
        ns: list = field(default_factory=list)

    return C


def reject_unsupported_list_metadata():
    @dataclass
    class C:
        ns: Annotated[list[int], Step(value=2)] = field(default_factory=list)

    return C


def reject_duplicate_union_options():
    @dataclass
    class C:
        n: Annotated[int, Min(value=0)] | Annotated[int, Max(value=9)]

    return C


def reject_mutable_list_default_in_function_style():
    return None


REJECT_CASES = [
    (reject_slider_without_bounds, ValueError, "slider requires min and max"),
    (reject_slider_with_only_min, ValueError, "slider requires min and max"),
    (reject_empty_range, ValueError, "empty range"),
    (reject_choice_below_min, ValueError, "below minimum"),
    (reject_choice_above_max, ValueError, "above maximum"),
    (reject_unknown_metadata_for_int, TypeError, "unsupported metadata for int"),
    (reject_default_below_min, ValueError, "too small"),
    (reject_default_above_max, ValueError, "too large"),
    (reject_default_not_in_choices, ValueError, "not a choice"),
    (reject_bool_default_on_int_field, TypeError, "expected int"),
    (reject_str_default_on_int_field, TypeError, "expected int"),
    (reject_none_default_without_none_option, TypeError, "expected int"),
    (reject_bare_list, TypeError, "list requires an item type"),
    (reject_unsupported_list_metadata, TypeError, "unsupported metadata for list"),
    (reject_duplicate_union_options, ValueError, "duplicate option types"),
]


@pytest.mark.parametrize(
    "case, exc, match", REJECT_CASES,
    ids=[c.__name__.removeprefix("reject_") for c, _, _ in REJECT_CASES],
)
def test_schema_rejected(case, exc, match):
    with pytest.raises(exc, match=match):
        struct_of(case())


ATOM_ERROR_CASES = [
    (lambda: Min(value="1"), TypeError, "must be orderable"),
    (lambda: Min(value=True), TypeError, "must be orderable"),
    (lambda: Max(value="1"), TypeError, "must be orderable"),
    (lambda: Step(value=0), ValueError, "must be > 0"),
    (lambda: Step(value=-1), ValueError, "must be > 0"),
    (lambda: Step(value=True), TypeError, "must be a number"),
    (lambda: Slider(show_value=1), TypeError, "must be bool"),
    (lambda: Placeholder(value=""), ValueError, "must not be empty"),
    (lambda: Placeholder(value=7), TypeError, "must be str"),
    (lambda: Choices(values=[1, 2]), TypeError, "must be tuple"),
    (lambda: Choices(values=()), ValueError, "must not be empty"),
    (lambda: Choices(values=(1, 1)), ValueError, "must not repeat"),
]


@pytest.mark.parametrize("build, exc, match", ATOM_ERROR_CASES,
                         ids=range(len(ATOM_ERROR_CASES)))
def test_atom_errors(build, exc, match):
    with pytest.raises(exc, match=match):
        build()


def test_int_rejects_pure_bool_choices():
    with pytest.raises(TypeError, match="expected int"):
        Int(choices=Choices(values=(True, False)))


def test_int_step_defaults_to_none():
    assert Int().step is None


def test_int_step_explicit_is_preserved():
    assert Int(step=Step(value=5)).step == Step(value=5)


def test_int_min_rejects_float_value():
    with pytest.raises(TypeError, match="Int.min: expected int, got float"):
        Int(min=Min(0.5))


def test_int_exclusive_min_rejects_boundary():
    with pytest.raises(ValueError, match=r"too small: 5, minimum 5 \(exclusive\)"):
        Int(min=Min(5, exclusive=True))._check(5)


def test_int_exclusive_min_accepts_above():
    Int(min=Min(5, exclusive=True))._check(6)


def test_int_exclusive_max_rejects_boundary():
    with pytest.raises(ValueError, match=r"too large: 5, maximum 5 \(exclusive\)"):
        Int(max=Max(5, exclusive=True))._check(5)


def test_int_exclusive_max_accepts_below():
    Int(max=Max(5, exclusive=True))._check(4)


def test_int_exclusive_both_empty_range():
    with pytest.raises(ValueError, match=r"empty range \(4\.\.5\)"):
        Int(min=Min(4, exclusive=True), max=Max(5, exclusive=True))


def test_int_exclusive_min_equals_inclusive_max_empty_range():
    with pytest.raises(ValueError, match=r"empty range \(5\.\.5\)"):
        Int(min=Min(5, exclusive=True), max=Max(5))


def test_int_exclusive_min_excludes_choice_at_boundary():
    with pytest.raises(ValueError, match="below minimum 0"):
        Int(min=Min(0, exclusive=True), choices=Choices(values=(0, 1)))


def test_bridge_exclusive_min_end_to_end():
    @dataclass
    class C:
        n: Annotated[int, Min(0, exclusive=True)] = 1

    schema = struct_of(C)
    with pytest.raises(ValueError, match="too small"):
        schema.resolve({"n": 0})
    assert schema.resolve({"n": 1}) == {"n": 1}


def test_multiple_of_check_passes_and_fails():
    Int(multiple_of=MultipleOf(5))._check(35)
    with pytest.raises(ValueError, match="not a multiple of 5"):
        Int(multiple_of=MultipleOf(5))._check(7)


def test_multiple_of_check_zero_passes():
    Int(multiple_of=MultipleOf(5))._check(0)


def test_multiple_of_check_negative_passes():
    Int(multiple_of=MultipleOf(5))._check(-10)


def test_multiple_of_empty_range_no_multiple():
    with pytest.raises(ValueError, match="no multiple"):
        Int(min=Min(1), max=Max(4), multiple_of=MultipleOf(5))


def test_multiple_of_range_with_multiple_compiles():
    Int(min=Min(1), max=Max(5), multiple_of=MultipleOf(5))


def test_multiple_of_negative_range_compiles():
    Int(min=Min(-7), max=Max(-1), multiple_of=MultipleOf(5))


def test_multiple_of_exclusive_min_still_reaches_multiple():
    Int(min=Min(4, exclusive=True), max=Max(5), multiple_of=MultipleOf(5))


def test_multiple_of_exclusive_both_bounds_is_empty_range():
    with pytest.raises(ValueError, match="empty range"):
        Int(min=Min(4, exclusive=True), max=Max(5, exclusive=True), multiple_of=MultipleOf(5))


def test_multiple_of_rejects_non_multiple_choice():
    with pytest.raises(ValueError, match="not a multiple"):
        Int(choices=Choices(values=(5, 10, 12)), multiple_of=MultipleOf(5))


def test_multiple_of_and_step_compose():
    Int(multiple_of=MultipleOf(5), step=Step(25))


def test_bridge_multiple_of_end_to_end():
    @dataclass
    class C:
        n: Annotated[int, MultipleOf(5)] = 5

    schema = struct_of(C)
    with pytest.raises(ValueError, match="not a multiple"):
        schema.resolve({"n": 7})
    assert schema.resolve({"n": 35}) == {"n": 35}

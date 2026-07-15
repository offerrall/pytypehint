from dataclasses import dataclass, field
from typing import Annotated

import pytest

from pytypehint.atoms import Choices, Description, Label, Max, Min, MultipleOf, Slider, Step
from pytypehint.bridge import struct_of
from pytypehint.shapes import Bool, Int, List, NoneShape
from pytypehint.structure import Field, Struct


def case_list_of_int():
    @dataclass
    class C:
        ns: list[int] = field(default_factory=list)

    return C, Struct(cls=C, fields=(
        Field(name="ns", shape=(List(item=(Int(),)),), default=[]),
    ))


def case_list_of_bool():
    @dataclass
    class C:
        flags: list[bool] = field(default_factory=list)

    return C, Struct(cls=C, fields=(
        Field(name="flags", shape=(List(item=(Bool(),)),), default=[]),
    ))


def case_list_of_dataclass():
    @dataclass
    class Inner:
        n: int = 0

    @dataclass
    class C:
        items: list[Inner] = field(default_factory=list)

    return C, Struct(cls=C, fields=(
        Field(
            name="items",
            shape=(List(item=(Struct(cls=Inner, fields=(
                Field(name="n", shape=(Int(),), default=0),
            )),)),),
            default=[],
        ),
    ))


def case_bounds_on_list_are_length():
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


def case_bounds_on_item_are_value():
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


def case_bounds_on_both_layers():
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


def case_item_with_choices():
    @dataclass
    class C:
        ns: list[Annotated[int, Choices(values=(1, 2, 3))]] = field(
            default_factory=lambda: [1, 1, 3]
        )

    return C, Struct(cls=C, fields=(
        Field(
            name="ns",
            shape=(List(item=(Int(choices=Choices(values=(1, 2, 3))),)),),
            default=[1, 1, 3],
        ),
    ))


def case_nested_lists():
    @dataclass
    class C:
        grid: list[list[int]] = field(default_factory=list)

    return C, Struct(cls=C, fields=(
        Field(name="grid", shape=(List(item=(List(item=(Int(),)),)),), default=[]),
    ))


def case_nested_lists_bounds_each_layer():
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


def case_optional_list():
    @dataclass
    class C:
        ns: list[int] | None = None

    return C, Struct(cls=C, fields=(
        Field(name="ns", shape=(List(item=(Int(),)), NoneShape()), default=None),
    ))


def case_list_with_field_atoms():
    @dataclass
    class C:
        ns: Annotated[
            list[int], Min(value=1), Label(value="Ns"), Description(value="al menos uno"),
        ] = field(default_factory=lambda: [0])

    return C, Struct(cls=C, fields=(
        Field(
            name="ns",
            shape=(List(item=(Int(),), min=Min(value=1)),),
            default=[0],
            label=Label(value="Ns"),
            description=Description(value="al menos uno"),
        ),
    ))


def case_min_equals_max_length():
    @dataclass
    class C:
        pair: Annotated[list[int], Min(value=2), Max(value=2)] = field(
            default_factory=lambda: [0, 0]
        )

    return C, Struct(cls=C, fields=(
        Field(
            name="pair",
            shape=(List(item=(Int(),), min=Min(value=2), max=Max(value=2)),),
            default=[0, 0],
        ),
    ))


def case_zero_length_allowed():
    @dataclass
    class C:
        ns: Annotated[list[int], Min(value=0), Max(value=0)] = field(default_factory=list)

    return C, Struct(cls=C, fields=(
        Field(
            name="ns",
            shape=(List(item=(Int(),), min=Min(value=0), max=Max(value=0)),),
            default=[],
        ),
    ))


SCHEMA_CASES = [
    case_list_of_int,
    case_list_of_bool,
    case_list_of_dataclass,
    case_bounds_on_list_are_length,
    case_bounds_on_item_are_value,
    case_bounds_on_both_layers,
    case_item_with_choices,
    case_nested_lists,
    case_nested_lists_bounds_each_layer,
    case_optional_list,
    case_list_with_field_atoms,
    case_min_equals_max_length,
    case_zero_length_allowed,
]


@pytest.mark.parametrize("case", SCHEMA_CASES, ids=lambda c: c.__name__.removeprefix("case_"))
def test_schema(case):
    cls, expected = case()
    assert repr(struct_of(cls).fields) == repr(expected.fields)


def test_default_factory_materializes_per_field_frozen():
    @dataclass
    class C:
        ns: list[int] = field(default_factory=lambda: [1, 2])

    (f,) = struct_of(C).fields
    assert f.default == [1, 2]            # 0.1.0: certified product is a list, not a frozen tuple
    assert type(f.default) is list


def reject_bare_list():
    @dataclass
    class C:
        ns: list = field(default_factory=list)

    return C


def reject_union_item():
    @dataclass
    class C:
        ns: list[int | None] = field(default_factory=list)

    return C


def reject_union_item_two_real_types():
    @dataclass
    class C:
        ns: list[int | bool] = field(default_factory=list)

    return C


def reject_none_item():
    @dataclass
    class C:
        ns: list[None] = field(default_factory=list)

    return C


def reject_unsupported_metadata():
    @dataclass
    class C:
        ns: Annotated[list[int], Step(value=2)] = field(default_factory=list)

    return C


def reject_slider_on_list():
    @dataclass
    class C:
        ns: Annotated[list[int], Slider()] = field(default_factory=list)

    return C


def reject_choices_on_list():
    @dataclass
    class C:
        ns: Annotated[list[int], Choices(values=(1, 2))] = field(default_factory=list)

    return C


def reject_default_too_short():
    @dataclass
    class C:
        ns: Annotated[list[int], Min(value=2)] = field(default_factory=lambda: [1])

    return C


def reject_default_too_long():
    @dataclass
    class C:
        ns: Annotated[list[int], Max(value=1)] = field(default_factory=lambda: [1, 2])

    return C


def reject_default_item_wrong_type():
    @dataclass
    class C:
        ns: list[int] = field(default_factory=lambda: [1, "x"])

    return C


def reject_default_item_out_of_range():
    @dataclass
    class C:
        ns: list[Annotated[int, Max(value=9)]] = field(default_factory=lambda: [1, 99])

    return C


def reject_default_bool_in_int_list():
    @dataclass
    class C:
        ns: list[int] = field(default_factory=lambda: [1, True])

    return C


def reject_default_not_a_list():
    @dataclass
    class C:
        ns: list[int] = 0

    return C


def reject_empty_length_range():
    @dataclass
    class C:
        ns: Annotated[list[int], Min(value=3), Max(value=1)] = field(default_factory=list)

    return C


def reject_negative_length():
    @dataclass
    class C:
        ns: Annotated[list[int], Min(value=-1)] = field(default_factory=list)

    return C


REJECT_CASES = [
    (reject_bare_list, TypeError, "list requires an item type"),
    (reject_none_item, TypeError, "cannot be NoneShape"),
    (reject_unsupported_metadata, TypeError, "unsupported metadata for list"),
    (reject_slider_on_list, TypeError, "unsupported metadata for list"),
    (reject_choices_on_list, TypeError, "unsupported metadata for list"),
    (reject_default_too_short, ValueError, "too few items"),
    (reject_default_too_long, ValueError, "too many items"),
    (reject_default_item_wrong_type, TypeError, r"\[1\]: expected int"),
    (reject_default_item_out_of_range, ValueError, r"\[1\]: too large"),
    (reject_default_bool_in_int_list, TypeError, r"\[1\]: expected int"),
    (reject_default_not_a_list, TypeError, "expected list"),
    (reject_empty_length_range, ValueError, "empty range"),
    (reject_negative_length, ValueError, "must be >= 0"),
]


@pytest.mark.parametrize(
    "case, exc, match", REJECT_CASES,
    ids=[c.__name__.removeprefix("reject_") for c, _, _ in REJECT_CASES],
)
def test_schema_rejected(case, exc, match):
    with pytest.raises(exc, match=match):
        struct_of(case())


CONSTRUCTION_ERRORS = [
    (lambda: List(item=(5,)), TypeError, "must be a non-empty tuple of shapes"),
    (lambda: List(item=(int,)), TypeError, "must be a non-empty tuple of shapes"),
    (lambda: List(item=(NoneShape(),)), TypeError, "cannot be NoneShape"),
    (lambda: List(item=(Int(),), min=Min(value=-1)), ValueError, "must be >= 0"),
    (lambda: List(item=(Int(),), max=Max(value=-1)), ValueError, "must be >= 0"),
    (lambda: List(item=(Int(),), min=Min(value=3), max=Max(value=1)), ValueError, "empty range"),
    (lambda: List(item=(Int(),), min=1), TypeError, "must be Min"),
    (lambda: List(item=(Int(),), max=9), TypeError, "must be Max"),
]


@pytest.mark.parametrize("build, exc, match", CONSTRUCTION_ERRORS,
                         ids=range(len(CONSTRUCTION_ERRORS)))
def test_construction_errors(build, exc, match):
    with pytest.raises(exc, match=match):
        build()


def test_zero_length_range_is_legal():
    s = List(item=(Int(),), min=Min(value=0), max=Max(value=0))
    s._check([])
    with pytest.raises(ValueError, match="too many items"):
        s._check([1])


def test_check_accepts():
    List(item=(Int(),))._check([])
    List(item=(Int(),))._check([1, 2, 3])
    List(item=(Bool(),))._check([True, False])
    List(item=(List(item=(Int(),)),))._check([[1], [], [2, 3]])


def test_check_rejects_non_list():
    for value in ((1, 2), {1: 2}, "abc", None, 5):
        with pytest.raises(TypeError, match="expected list"):
            List(item=(Int(),))._check(value)


def test_check_rejects_tuple_even_though_iterable():
    with pytest.raises(TypeError, match="expected list"):
        List(item=(Int(),))._check((1, 2))


def test_check_length_bounds():
    s = List(item=(Int(),), min=Min(value=1), max=Max(value=3))
    s._check([1])
    s._check([1, 2, 3])

    with pytest.raises(ValueError, match="too few items: 0, minimum 1"):
        s._check([])
    with pytest.raises(ValueError, match="too many items: 4, maximum 3"):
        s._check([1, 2, 3, 4])


def test_check_reports_first_bad_index():
    with pytest.raises(TypeError, match=r"^\[2\]: expected int"):
        List(item=(Int(),))._check([1, 2, "x", 4])


def test_check_index_zero():
    with pytest.raises(TypeError, match=r"^\[0\]: expected int"):
        List(item=(Int(),))._check(["x"])


# --- list[list[X]] behavior: happy path, per-level bounds, double-index error,
#     freshness at every level (vocabulary.md "list") ---


def test_nested_list_happy_path_and_inner_bound():
    @dataclass
    class Grid:
        rows: list[Annotated[list[int], Min(value=1)]] = field(default_factory=list)

    g = struct_of(Grid)
    assert g.resolve({"rows": [[1, 2], [3]]}) == {"rows": [[1, 2], [3]]}
    with pytest.raises(ValueError, match=r"^rows: \[0\]: too few items: 0, minimum 1$"):
        g.resolve({"rows": [[]]})


def test_nested_list_double_index_type_error():
    @dataclass
    class Grid:
        rows: list[list[int]] = field(default_factory=list)

    with pytest.raises(TypeError, match=r"^rows: \[1\]: \[0\]: expected int, got str$"):
        struct_of(Grid).resolve({"rows": [[1], ["x", 2]]})


def test_nested_list_default_is_fresh_at_both_levels():
    @dataclass
    class Grid:
        rows: list[list[int]] = field(default_factory=lambda: [[1], [2]])

    g = struct_of(Grid)
    a = g.build({})
    b = g.build({})
    assert a.rows == b.rows == [[1], [2]]   # same recipe, same dish
    assert a.rows is not b.rows             # outer list fresh
    assert a.rows[0] is not b.rows[0]       # inner list fresh too


def test_check_item_constraint_carries_index():
    s = List(item=(Int(min=Min(value=0), max=Max(value=9)),))
    s._check([0, 9])

    with pytest.raises(ValueError, match=r"^\[1\]: too large: 99"):
        s._check([5, 99])
    with pytest.raises(ValueError, match=r"^\[0\]: too small: -1"):
        s._check([-1, 5])


def test_check_nested_index_chains():
    s = List(item=(List(item=(Int(),)),))
    s._check([[1, 2], [3]])

    with pytest.raises(TypeError, match=r"^\[1\]: \[0\]: expected int"):
        s._check([[1], ["x"]])


def test_check_nested_index_chains_three_deep():
    s = List(item=(List(item=(List(item=(Int(),)),)),))
    with pytest.raises(TypeError, match=r"^\[0\]: \[1\]: \[2\]: expected int"):
        s._check([[[1], [1, 2, "x"]]])


def test_check_nested_length_bound_carries_index():
    s = List(item=(List(item=(Int(),), max=Max(value=2)),))
    with pytest.raises(ValueError, match=r"^\[1\]: too many items: 3, maximum 2"):
        s._check([[1], [1, 2, 3]])


def test_check_bool_is_not_int_item():
    with pytest.raises(TypeError, match=r"^\[0\]: expected int"):
        List(item=(Int(),))._check([True])


def test_check_length_before_items():
    s = List(item=(Int(),), max=Max(value=1))
    with pytest.raises(ValueError, match="too many items"):
        s._check([1, "x"])


def test_list_of_struct_check():
    @dataclass
    class Inner:
        n: Annotated[int, Min(value=0)] = 0

    @dataclass
    class C:
        items: list[Inner] = field(default_factory=list)

    s = struct_of(C)
    s._check(C())
    s._check(C(items=[Inner(n=1), Inner(n=2)]))


def test_list_of_struct_reports_index_and_field():
    @dataclass
    class Inner:
        n: Annotated[int, Min(value=0)] = 0

    @dataclass
    class C:
        items: list[Inner] = field(default_factory=list)

    s = struct_of(C)
    with pytest.raises(ValueError, match=r"items: \[1\]: n: too small"):
        s._check(C(items=[Inner(n=0), Inner(n=-5)]))


def test_list_of_struct_rejects_wrong_class():
    @dataclass
    class Inner:
        n: int = 0

    @dataclass
    class Other:
        n: int = 0

    @dataclass
    class C:
        items: list[Inner] = field(default_factory=list)

    s = struct_of(C)
    with pytest.raises(TypeError, match=r"items: \[0\]: expected Inner, got Other"):
        s._check(C(items=[Other()]))


def test_optional_list_dispatch():
    f = Field(name="ns", shape=(List(item=(Int(),), min=Min(value=1)), NoneShape()), default=None)
    f._check_value(None)
    f._check_value([1])

    with pytest.raises(ValueError, match="too few items"):
        f._check_value([])

    with pytest.raises(TypeError, match="expected list | NoneType"):
        f._check_value(5)


def test_list_min_stays_int():
    with pytest.raises(TypeError, match="List.min: expected int, got float"):
        List(item=(Int(),), min=Min(0.5))


def test_list_min_rejects_exclusive():
    with pytest.raises(ValueError, match="exclusive bounds are not supported for lengths"):
        List(item=(Int(),), min=Min(1, exclusive=True))


def test_list_max_rejects_exclusive():
    with pytest.raises(ValueError, match="exclusive bounds are not supported for lengths"):
        List(item=(Int(),), max=Max(3, exclusive=True))


def test_list_rejects_multiple_of_as_metadata():
    @dataclass
    class C:
        ns: Annotated[list[int], MultipleOf(5)] = field(default_factory=list)

    with pytest.raises(TypeError, match="unsupported metadata"):
        struct_of(C)


def test_multiple_of_on_list_item_compiles():
    @dataclass
    class C:
        ns: list[Annotated[int, MultipleOf(5)]] = field(default_factory=list)

    assert struct_of(C).fields[0].shape[0] == List(item=(Int(multiple_of=MultipleOf(5)),))

from dataclasses import FrozenInstanceError, dataclass, field
from typing import Annotated

import pytest

from pytypehint.atoms import (
    Choices, Description, Label, Max, Min, Placeholder, Slider, Step,
)
from pytypehint.bridge import struct_of
from pytypehint.shapes import Bool, Int, List, NoneShape, Shape
from pytypehint.structure import Field, Struct
from pytypehint.utils import MISSING


def test_bool_default_rejected_on_int():
    @dataclass
    class C:
        n: int = True

    with pytest.raises(TypeError, match="expected int"):
        struct_of(C)


def test_int_default_rejected_on_bool():
    @dataclass
    class C:
        b: bool = 1

    with pytest.raises(TypeError, match="expected bool"):
        struct_of(C)


def test_bool_inside_int_list_default():
    @dataclass
    class C:
        ns: list[int] = field(default_factory=lambda: [1, True, 3])

    with pytest.raises(TypeError, match=r"\[1\]: expected int"):
        struct_of(C)


def test_int_inside_bool_list_default():
    @dataclass
    class C:
        flags: list[bool] = field(default_factory=lambda: [True, 0])

    with pytest.raises(TypeError, match=r"\[1\]: expected bool"):
        struct_of(C)


def test_union_int_bool_dispatches_by_exact_type():
    @dataclass
    class C:
        x: int | bool = 0

    f = struct_of(C).fields[0]
    f._check_value(0)
    f._check_value(False)
    f._check_value(1)
    f._check_value(True)


def test_union_int_bool_default_zero_is_int_not_false():
    @dataclass
    class C:
        x: int | bool = 0

    f = struct_of(C).fields[0]
    assert f.default == 0
    assert type(f.default) is int


def test_union_int_bool_constraint_only_hits_the_int_option():
    @dataclass
    class C:
        x: Annotated[int, Min(value=10)] | bool = True

    f = struct_of(C).fields[0]
    f._check_value(True)
    f._check_value(False)
    f._check_value(10)

    with pytest.raises(ValueError, match="too small"):
        f._check_value(5)


def test_bool_choices_do_not_collapse_into_int():
    # int and bool are distinct types: not a repeat. The type mix surfaces at
    # the shape as "expected int, got bool", not a misleading "must not repeat".
    Choices(values=(1, True))
    Choices(values=(0, False))

    with pytest.raises(TypeError, match="expected int"):
        Int(choices=Choices(values=(1, True)))

    with pytest.raises(TypeError, match="expected int"):
        Int(choices=Choices(values=(True, False)))


def test_cross_type_choice_reports_the_real_type_error():
    # 1 and 1.0 pass the atom (distinct types, no repeat); the mix surfaces as
    # the true type error at the shape, not a misleading "must not repeat".
    with pytest.raises(TypeError, match="Int.choices: expected int, got float"):
        Int(choices=Choices(values=(1, 1.0)))


DEFAULT_REJECTS = [
    ("below_min", lambda: _dc(Annotated[int, Min(value=10)], 5), ValueError, "too small"),
    ("above_max", lambda: _dc(Annotated[int, Max(value=10)], 50), ValueError, "too large"),
    ("not_a_choice", lambda: _dc(Annotated[int, Choices(values=(1, 2))], 3), ValueError, "not a choice"),
    ("str_on_int", lambda: _dc(int, "7"), TypeError, "expected int"),
    ("float_on_int", lambda: _dc(int, 1.0), TypeError, "expected int"),
    ("none_on_int", lambda: _dc(int, None), TypeError, "expected int"),
    ("int_on_list", lambda: _dc(list[int], 0), TypeError, "expected list"),
]


def _dc(hint, default):
    ns = {"__annotations__": {"x": hint}, "x": default}
    return dataclass(type("C", (), ns))


@pytest.mark.parametrize("name, build, exc, match", DEFAULT_REJECTS,
                         ids=[n for n, _, _, _ in DEFAULT_REJECTS])
def test_default_must_fit_the_shape(name, build, exc, match):
    with pytest.raises(exc, match=match):
        struct_of(build())


def test_default_at_the_exact_boundary_passes():
    @dataclass
    class C:
        lo: Annotated[int, Min(value=0), Max(value=10)] = 0
        hi: Annotated[int, Min(value=0), Max(value=10)] = 10

    struct_of(C)


def test_default_one_past_the_boundary_fails():
    @dataclass
    class C:
        n: Annotated[int, Min(value=0), Max(value=10)] = 11

    with pytest.raises(ValueError, match="too large: 11"):
        struct_of(C)


def test_step_does_not_constrain_the_default():
    @dataclass
    class C:
        n: Annotated[int, Step(value=5)] = 7

    assert struct_of(C).fields[0].default == 7


def test_step_does_not_constrain_check():
    Int(step=Step(value=5))._check(7)


def test_negative_default_with_negative_bounds():
    @dataclass
    class C:
        n: Annotated[int, Min(value=-10), Max(value=-1)] = -5

    struct_of(C)._check(C())

    with pytest.raises(ValueError, match="too large: 0"):
        struct_of(C)._check(C(n=0))


def test_zero_is_a_valid_default_not_a_missing_one():
    @dataclass
    class C:
        a: int = 0
        b: bool = False
        c: list[int] = field(default_factory=list)

    for f in struct_of(C).fields:
        assert f.default is not MISSING


def test_missing_is_not_none():
    @dataclass
    class C:
        required: int
        optional: int | None = None

    a, b = struct_of(C).fields
    assert a.default is MISSING
    assert b.default is None
    assert MISSING is not None


def test_list_default_validates_every_item():
    @dataclass
    class C:
        ns: list[Annotated[int, Min(value=0), Max(value=9)]] = field(
            default_factory=lambda: [0, 5, 9]
        )

    struct_of(C)


def test_list_default_reports_the_first_bad_item():
    @dataclass
    class C:
        ns: list[Annotated[int, Max(value=9)]] = field(
            default_factory=lambda: [1, 99, 999]
        )

    with pytest.raises(ValueError, match=r"\[1\]: too large: 99"):
        struct_of(C)


def test_list_default_length_checked_before_items():
    @dataclass
    class C:
        ns: Annotated[list[Annotated[int, Max(value=9)]], Max(value=1)] = field(
            default_factory=lambda: [99, 99]
        )

    with pytest.raises(ValueError, match="too many items"):
        struct_of(C)


def test_empty_list_default_against_min_length():
    @dataclass
    class C:
        ns: Annotated[list[int], Min(value=1)] = field(default_factory=list)

    with pytest.raises(ValueError, match="too few items: 0"):
        struct_of(C)


def test_nested_list_default_chains_indices():
    @dataclass
    class C:
        grid: list[list[Annotated[int, Max(value=9)]]] = field(
            default_factory=lambda: [[1, 2], [3, 99]]
        )

    with pytest.raises(ValueError, match=r"\[1\]: \[1\]: too large: 99"):
        struct_of(C)


def test_list_default_with_mixed_types():
    @dataclass
    class C:
        ns: list[int] = field(default_factory=lambda: [1, "2", 3])

    with pytest.raises(TypeError, match=r"\[1\]: expected int"):
        struct_of(C)


def test_optional_list_default_none_skips_length_check():
    @dataclass
    class C:
        ns: Annotated[list[int], Min(value=2)] | None = None

    struct_of(C)


def test_optional_list_empty_is_not_none():
    @dataclass
    class C:
        ns: Annotated[list[int], Min(value=2)] | None = None

    f = struct_of(C).fields[0]
    f._check_value(None)

    with pytest.raises(ValueError, match="too few items"):
        f._check_value([])


def test_list_of_struct_default_validates_instances():
    @dataclass
    class Item:
        n: Annotated[int, Min(value=0)] = 0

    @dataclass
    class C:
        items: list[Item] = field(default_factory=lambda: [Item(0), Item(-1)])

    with pytest.raises(ValueError, match=r"\[1\]: n: too small"):
        struct_of(C)


def test_choices_within_bounds_is_fine():
    Int(min=Min(value=0), max=Max(value=10), choices=Choices(values=(0, 5, 10)))


def test_choices_outside_bounds_rejected():
    with pytest.raises(ValueError, match="below minimum"):
        Int(min=Min(value=5), choices=Choices(values=(1,)))
    with pytest.raises(ValueError, match="above maximum"):
        Int(max=Max(value=5), choices=Choices(values=(9,)))


def test_choices_at_the_exact_bounds():
    Int(min=Min(value=0), max=Max(value=10), choices=Choices(values=(0, 10)))


def test_single_choice_is_legal():
    s = Int(choices=Choices(values=(42,)))
    s._check(42)
    with pytest.raises(ValueError, match="not a choice"):
        s._check(41)


def test_degenerate_range_one_legal_value():
    s = Int(min=Min(value=5), max=Max(value=5))
    s._check(5)
    with pytest.raises(ValueError, match="too small"):
        s._check(4)
    with pytest.raises(ValueError, match="too large"):
        s._check(6)


def test_slider_needs_both_bounds():
    Int(min=Min(value=0), max=Max(value=10), slider=Slider())

    with pytest.raises(ValueError, match="slider requires min and max"):
        Int(slider=Slider())
    with pytest.raises(ValueError, match="slider requires min and max"):
        Int(min=Min(value=0), slider=Slider())
    with pytest.raises(ValueError, match="slider requires min and max"):
        Int(max=Max(value=10), slider=Slider())


def test_slider_with_choices_is_allowed_but_odd():
    Int(min=Min(value=0), max=Max(value=10), choices=Choices(values=(0, 5, 10)),
        slider=Slider())


def test_slider_and_placeholder_together():
    Int(min=Min(value=0), max=Max(value=10), slider=Slider(),
        placeholder=Placeholder(value="0-10"))


def test_all_int_atoms_at_once():
    @dataclass
    class C:
        n: Annotated[
            int,
            Min(value=0), Max(value=100), Choices(values=(0, 25, 50, 75, 100)),
            Step(value=25), Slider(show_value=False), Placeholder(value="pick"),
            Label(value="N"), Description(value="d"),
        ] = 50

    s = struct_of(C)
    shape = s.fields[0].shape[0]
    assert shape.min == Min(value=0)
    assert shape.max == Max(value=100)
    assert shape.choices == Choices(values=(0, 25, 50, 75, 100))
    assert shape.step == Step(value=25)
    assert shape.slider == Slider(show_value=False)
    assert shape.placeholder == Placeholder(value="pick")
    assert s.fields[0].label == Label(value="N")
    assert s.fields[0].description == Description(value="d")


def test_empty_range_beats_everything():
    with pytest.raises(ValueError, match="empty range"):
        Int(min=Min(value=10), max=Max(value=1),
            choices=Choices(values=(5,)), slider=Slider())


def test_three_way_union():
    @dataclass
    class C:
        x: int | bool | None = None

    f = struct_of(C).fields[0]
    assert len(f.shape) == 3
    f._check_value(0)
    f._check_value(True)
    f._check_value(None)

    with pytest.raises(TypeError, match="expected int"):
        f._check_value("x")


def test_union_of_list_and_int():
    @dataclass
    class C:
        x: list[int] | int = 0

    f = struct_of(C).fields[0]
    f._check_value(5)
    f._check_value([1, 2])

    with pytest.raises(TypeError):
        f._check_value(None)


def test_union_of_two_dataclasses():
    @dataclass
    class A:
        n: int = 0

    @dataclass
    class B:
        b: bool = False

    @dataclass
    class C:
        x: A | B = field(default_factory=A)

    f = struct_of(C).fields[0]
    f._check_value(A())
    f._check_value(B())

    with pytest.raises(TypeError, match="expected A | B"):
        f._check_value(5)


def test_duplicate_option_types_rejected():
    @dataclass
    class C:
        x: Annotated[int, Min(value=0)] | Annotated[int, Max(value=9)] = 0

    with pytest.raises(ValueError, match="duplicate option types"):
        struct_of(C)


def test_union_with_same_dataclass_twice_collapses_in_typing():
    @dataclass
    class A:
        n: int = 0

    @dataclass
    class C:
        x: A | A = field(default_factory=A)

    assert len(struct_of(C).fields[0].shape) == 1


def test_option_order_is_preserved():
    @dataclass
    class C:
        x: None | int = None

    shape = struct_of(C).fields[0].shape
    assert type(shape[0]) is NoneShape
    assert type(shape[1]) is Int


def test_field_named_like_a_shape():
    @dataclass
    class C:
        Int: int = 0
        List: bool = False

    s = struct_of(C)
    assert [f.name for f in s.fields] == ["Int", "List"]
    s._check(C())


def test_field_named_check():
    @dataclass
    class C:
        check: int = 0

    struct_of(C)._check(C())


def test_field_named_cls_and_fields():
    @dataclass
    class C:
        cls: int = 0
        fields: bool = False

    struct_of(C)._check(C())


def test_dunder_name_rejected_by_field():
    Field(name="_private", shape=(Int(),))

    with pytest.raises(ValueError, match="must be an identifier"):
        Field(name="2x", shape=(Int(),))
    with pytest.raises(ValueError, match="must be an identifier"):
        Field(name="a b", shape=(Int(),))
    with pytest.raises(ValueError, match="must be an identifier"):
        Field(name="", shape=(Int(),))


def test_type_error_before_range_error():
    with pytest.raises(TypeError, match="expected int"):
        Int(min=Min(value=0))._check("5")


def test_min_before_max():
    s = Int(min=Min(value=0), max=Max(value=10))
    with pytest.raises(ValueError, match="too small"):
        s._check(-1)


def test_bounds_before_choices():
    s = Int(min=Min(value=0), max=Max(value=10), choices=Choices(values=(5,)))
    with pytest.raises(ValueError, match="too large"):
        s._check(99)


def test_list_type_before_length():
    with pytest.raises(TypeError, match="expected list"):
        List(item=(Int(),), min=Min(value=1))._check("abc")


def test_struct_type_before_fields():
    @dataclass
    class A:
        n: Annotated[int, Min(value=0)] = 0

    @dataclass
    class B:
        n: int = -1

    with pytest.raises(TypeError, match="expected A, got B"):
        struct_of(A)._check(B())


def test_first_field_wins():
    @dataclass
    class C:
        a: Annotated[int, Min(value=0)] = 0
        b: Annotated[int, Min(value=0)] = 0

    with pytest.raises(ValueError, match=r"^a: too small"):
        struct_of(C)._check(C(a=-1, b=-2))


def test_shapes_are_frozen():

    s = Int(min=Min(value=0))
    with pytest.raises(FrozenInstanceError):
        s.min = Min(value=5)


def test_atoms_are_frozen():

    with pytest.raises(FrozenInstanceError):
        Min(value=0).value = 5


def test_equal_shapes_are_interchangeable():
    assert Int(min=Min(value=0)) == Int(min=Min(value=0))
    assert Int(min=Min(value=0)) != Int(min=Min(value=1))
    assert Bool() == Bool()
    assert NoneShape() == NoneShape()
    assert List(item=(Int(),)) == List(item=(Int(),))
    assert List(item=(Int(),)) != List(item=(Bool(),))


def test_shapes_are_hashable():
    {Int(), Bool(), NoneShape(), List(item=(Int(),)), Min(value=0)}


def test_two_compilations_have_distinct_identity():
    @dataclass
    class C:
        n: Annotated[int, Min(value=0)] = 0

    assert struct_of(C) != struct_of(C)


def test_same_shape_different_class_not_equal():
    @dataclass
    class A:
        n: int = 0

    @dataclass
    class B:
        n: int = 0

    assert struct_of(A) != struct_of(B)


def test_shape_subclass_requires_pytype():
    with pytest.raises(TypeError, match="must declare pytype"):
        class Broken(Shape):
            pass


def test_all_concrete_shapes_declare_pytype():
    for cls in (Int, Bool, NoneShape, List):
        assert hasattr(cls, "pytype")
        assert type(cls.pytype) is type


def test_struct_pytype_is_cls():
    @dataclass
    class C:
        n: int = 0

    schema = struct_of(C)
    assert schema.pytype is C

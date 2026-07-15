from dataclasses import dataclass, field
from datetime import date, time
from typing import Annotated

import pytest

from pytypehint.atoms import Choices, Max, Min, MultipleOf, Slider, Step
from pytypehint.bridge import struct_of
from pytypehint.shapes import Float, Int, List, NoneShape


def test_check_accepts_float():
    Float()._check(1.5)


def test_check_rejects_int():
    with pytest.raises(TypeError, match="expected float, got int"):
        Float()._check(1)


def test_check_rejects_bool():
    with pytest.raises(TypeError, match="expected float, got bool"):
        Float()._check(True)


def test_check_rejects_nan():
    with pytest.raises(ValueError, match="not finite"):
        Float()._check(float("nan"))


def test_check_rejects_inf():
    with pytest.raises(ValueError, match="not finite"):
        Float()._check(float("inf"))


def test_check_rejects_negative_inf():
    with pytest.raises(ValueError, match="not finite"):
        Float()._check(float("-inf"))


def test_min_inclusive_boundary_passes():
    Float(min=Min(0.5))._check(0.5)


def test_min_inclusive_below_fails():
    with pytest.raises(ValueError, match="too small"):
        Float(min=Min(0.5))._check(0.4)


def test_min_exclusive_boundary_fails():
    with pytest.raises(ValueError, match=r"too small: 0.5, minimum 0.5 \(exclusive\)"):
        Float(min=Min(0.5, exclusive=True))._check(0.5)


def test_min_exclusive_above_passes():
    Float(min=Min(0.5, exclusive=True))._check(0.6)


def test_int_atom_bound_on_float_shape():
    Float(min=Min(0))._check(0.0)


def test_empty_range_min_above_max():
    with pytest.raises(ValueError, match=r"empty range \(1.0\.\.0.5\)"):
        Float(min=Min(1.0), max=Max(0.5))


def test_equal_bounds_compile():
    Float(min=Min(1.0), max=Max(1.0))


def test_equal_bounds_with_exclusive_is_empty():
    with pytest.raises(ValueError, match="empty range"):
        Float(min=Min(1.0, exclusive=True), max=Max(1.0))


def test_non_finite_min_bound_rejected():
    with pytest.raises(ValueError, match="must be finite"):
        Float(min=Min(float("inf")))


def test_choices_membership():
    Float(choices=Choices(values=(0.5, 1.5)))._check(0.5)
    with pytest.raises(ValueError, match="not a choice"):
        Float(choices=Choices(values=(0.5, 1.5)))._check(1.0)


def test_choices_reject_int_value():
    with pytest.raises(TypeError, match="expected float"):
        Float(choices=Choices(values=(1,)))


def test_choices_reject_non_finite():
    with pytest.raises(ValueError, match="must be finite"):
        Float(choices=Choices(values=(float("nan"),)))


def test_slider_requires_bounds():
    with pytest.raises(ValueError, match="slider requires min and max"):
        Float(slider=Slider())


def test_slider_with_bounds_compiles():
    Float(min=Min(0.0), max=Max(1.0), slider=Slider())


def test_step_accepts_float():
    Step(0.1)


def test_step_rejects_zero():
    with pytest.raises(ValueError, match="must be > 0"):
        Step(0.0)


def test_step_rejects_negative():
    with pytest.raises(ValueError, match="must be > 0"):
        Step(-0.5)


def test_float_accepts_float_step():
    Float(step=Step(0.1))


def test_int_rejects_float_step():
    with pytest.raises(TypeError, match="expected int, got float"):
        Int(step=Step(0.1))


def test_bridge_float_end_to_end():
    @dataclass
    class C:
        x: Annotated[float, Min(0.0), Max(1.0), Step(0.1)] = 0.5

    schema = struct_of(C)
    assert schema.resolve({"x": 0.5}) == {"x": 0.5}
    with pytest.raises(ValueError, match="too large"):
        schema.resolve({"x": 2.0})
    with pytest.raises(TypeError, match="expected float, got int"):
        schema.resolve({"x": 1})
    with pytest.raises(ValueError, match="not finite"):
        schema.resolve({"x": float("nan")})


def test_bridge_optional_float():
    @dataclass
    class C:
        x: float | None = None

    schema = struct_of(C)
    assert schema.fields[0].shape == (Float(), NoneShape())
    assert schema.resolve({"x": None}) == {"x": None}
    assert schema.resolve({"x": 0.5}) == {"x": 0.5}


def test_bridge_list_of_float():
    @dataclass
    class C:
        xs: list[float] = field(default_factory=list)

    schema = struct_of(C)
    assert schema.fields[0].shape == (List(item=(Float(),)),)
    with pytest.raises(TypeError, match="expected float, got int"):
        schema.resolve({"xs": [1]})
    assert schema.resolve({"xs": [1.0]}) == {"xs": [1.0]}


def test_bridge_int_or_float_union():
    @dataclass
    class C:
        v: int | float = 0

    schema = struct_of(C)
    assert schema.fields[0].shape == (Int(), Float())
    assert schema.resolve({"v": 1}) == {"v": 1}
    assert schema.resolve({"v": 1.0}) == {"v": 1.0}


def test_bridge_multiple_of_rejected_on_float():
    @dataclass
    class C:
        x: Annotated[float, MultipleOf(2)] = 0.0

    with pytest.raises(TypeError, match="unsupported metadata"):
        struct_of(C)


def test_struct_float_default():
    @dataclass
    class C:
        x: float = 0.5

    struct_of(C)


def test_struct_int_default_on_float_fails():
    @dataclass
    class C:
        x: float = 1

    with pytest.raises(TypeError, match="expected float"):
        struct_of(C)


def test_float_min_bound_date_rejected_with_clean_message():
    with pytest.raises(TypeError, match="Float.min: expected int or float, got date"):
        Float(min=Min(date(2020, 1, 1)))


def test_float_max_bound_time_rejected_with_clean_message():
    with pytest.raises(TypeError, match="Float.max: expected int or float, got time"):
        Float(max=Max(time(9, 0)))


def test_float_int_bound_is_legal():
    Float(min=Min(0))


def test_float_int_bound_validates_values():
    Float(min=Min(0))._check(0.5)


def test_float_choice_date_rejected_with_clean_message():
    with pytest.raises(TypeError, match="Float.choices: expected float, got date"):
        Float(choices=Choices(values=(date(2020, 1, 1),)))


def test_bridge_float_bound_date_fails_with_clean_message():
    @dataclass
    class C:
        x: Annotated[float, Min(date(2020, 1, 1))] = 0.0

    with pytest.raises(TypeError, match="Float.min: expected int or float, got date"):
        struct_of(C)

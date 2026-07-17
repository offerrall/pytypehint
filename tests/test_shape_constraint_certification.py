from datetime import date, datetime, time, timezone
from enum import Enum, Flag

import pytest

from pytypehint import Choices, Max, Min, MultipleOf, Slider, Step
from pytypehint.shapes import Date, EnumShape, Float, Int, List, NoneShape, Str, Time


def test_int_max_bound_must_be_int():
    with pytest.raises(TypeError, match="Int.max: expected int"):
        Int(max=Max(1.5))


def test_str_min_bound_must_be_int():
    with pytest.raises(TypeError, match="Str.min: expected int"):
        Str(min=Min(1.5))


def test_str_max_bound_must_be_int():
    with pytest.raises(TypeError, match="Str.max: expected int"):
        Str(max=Max(1.5))


def test_str_max_exclusive_rejected_for_length():
    with pytest.raises(ValueError, match="Str.max: exclusive bounds are not supported for lengths"):
        Str(max=Max(3, exclusive=True))


def test_str_max_length_must_be_non_negative():
    with pytest.raises(ValueError, match="Str.max must be >= 0"):
        Str(max=Max(-1))


def test_str_choice_longer_than_maximum():
    with pytest.raises(ValueError, match="longer than maximum"):
        Str(max=Max(2), choices=Choices(values=("abc",)))


def test_float_max_bound_must_be_finite():
    with pytest.raises(ValueError, match="Float.max: must be finite"):
        Float(max=Max(float("inf")))


def test_float_choice_below_minimum():
    with pytest.raises(ValueError, match="below minimum"):
        Float(min=Min(0.0), choices=Choices(values=(-1.0,)))


def test_float_choice_above_maximum():
    with pytest.raises(ValueError, match="above maximum"):
        Float(max=Max(10.0), choices=Choices(values=(20.0,)))


def test_date_max_bound_must_be_date():
    with pytest.raises(TypeError, match="Date.max: expected date"):
        Date(max=Max(0))


def test_date_choice_above_maximum():
    with pytest.raises(ValueError, match="above maximum"):
        Date(max=Max(date(2020, 1, 1)), choices=Choices(values=(date(2020, 1, 2),)))


def test_time_max_bound_must_be_time():
    with pytest.raises(TypeError, match="Time.max: expected time"):
        Time(max=Max(0))


def test_time_min_bound_must_be_naive():
    with pytest.raises(ValueError, match="Time.min: must be naive"):
        Time(min=Min(time(9, 0, tzinfo=timezone.utc)))


def test_time_max_bound_must_be_naive():
    with pytest.raises(ValueError, match="Time.max: must be naive"):
        Time(max=Max(time(9, 0, tzinfo=timezone.utc)))


def test_time_choice_must_be_time():
    with pytest.raises(TypeError, match="Time.choices: expected time"):
        Time(choices=Choices(values=(0,)))


def test_time_choice_below_minimum():
    with pytest.raises(ValueError, match="below minimum"):
        Time(min=Min(time(9, 0)), choices=Choices(values=(time(8, 0),)))


def test_time_choice_above_maximum():
    with pytest.raises(ValueError, match="above maximum"):
        Time(max=Max(time(9, 0)), choices=Choices(values=(time(10, 0),)))


def test_list_max_length_must_be_int():
    with pytest.raises(TypeError, match="List.max: expected int"):
        List(item=(Int(),), max=Max(1.5))


@pytest.mark.parametrize("bad", [1.5, date(2020, 1, 1), time(9, 0)])
def test_int_min_bound_must_be_int(bad):
    with pytest.raises(TypeError, match="Int.min: expected int"):
        Int(min=Min(bad))


@pytest.mark.parametrize("bad", [1.5, 2.0, 0.5])
def test_int_step_must_be_int(bad):
    with pytest.raises(TypeError, match="Int.step: expected int"):
        Int(step=Step(bad))


@pytest.mark.parametrize("lo,hi", [(5, 4), (1, 0), (100, -100), (0, -1)])
def test_int_empty_range(lo, hi):
    with pytest.raises(ValueError, match="empty range"):
        Int(min=Min(lo), max=Max(hi))


@pytest.mark.parametrize("lo,hi", [(1, 4), (6, 9), (2, 3)])
def test_int_no_multiple_in_range(lo, hi):
    with pytest.raises(ValueError, match="no multiple of 5"):
        Int(min=Min(lo), max=Max(hi), multiple_of=MultipleOf(5))


def test_int_choice_not_a_multiple():
    with pytest.raises(ValueError, match="not a multiple"):
        Int(multiple_of=MultipleOf(3), choices=Choices(values=(3, 4)))


@pytest.mark.parametrize("shape_kwargs", [
    {"min": Min(0)},
    {"max": Max(10)},
    {},
])
def test_int_slider_requires_both_bounds(shape_kwargs):
    with pytest.raises(ValueError, match="slider requires min and max"):
        Int(slider=Slider(), **shape_kwargs)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_float_min_must_be_finite(bad):
    with pytest.raises(ValueError, match="Float.min: must be finite"):
        Float(min=Min(bad))


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_float_choice_must_be_finite(bad):
    with pytest.raises(ValueError, match="must be finite"):
        Float(choices=Choices(values=(bad,)))


def test_float_choice_wrong_type():
    with pytest.raises(TypeError, match="Float.choices: expected float"):
        Float(choices=Choices(values=(1,)))


@pytest.mark.parametrize("bad", [0, 1.5, time(9, 0)])
def test_date_min_bound_must_be_date(bad):
    with pytest.raises(TypeError, match="Date.min: expected date"):
        Date(min=Min(bad))


@pytest.mark.parametrize("choice", [0, "2020", 1.5, datetime(2020, 1, 1)])
def test_date_choice_wrong_type(choice):
    with pytest.raises(TypeError, match="Date.choices: expected date"):
        Date(choices=Choices(values=(choice,)))


@pytest.mark.parametrize("bad", [0, 1.5, date(2020, 1, 1)])
def test_time_min_bound_must_be_time(bad):
    with pytest.raises(TypeError, match="Time.min: expected time"):
        Time(min=Min(bad))


def test_date_empty_range_one_side_exclusive():
    with pytest.raises(ValueError, match="empty range"):
        Date(min=Min(date(2020, 1, 1), exclusive=True), max=Max(date(2020, 1, 1)))


@pytest.mark.parametrize("kw", [
    {"min": Min(time(9, 0), exclusive=True), "max": Max(time(9, 0))},
    {"min": Min(time(9, 0)), "max": Max(time(9, 0), exclusive=True)},
    {"min": Min(time(10, 0)), "max": Max(time(9, 0))},
])
def test_time_empty_range_variants(kw):
    with pytest.raises(ValueError, match="empty range"):
        Time(**kw)


@pytest.mark.parametrize("bad", [1.5, date(2020, 1, 1)])
def test_list_min_bound_must_be_int(bad):
    with pytest.raises(TypeError, match="List.min: expected int"):
        List(item=(Int(),), min=Min(bad))


def test_list_min_exclusive_rejected():
    with pytest.raises(ValueError, match="exclusive bounds are not supported for lengths"):
        List(item=(Int(),), min=Min(2, exclusive=True))


@pytest.mark.parametrize("n", [-1, -10])
def test_list_negative_length_rejected(n):
    with pytest.raises(ValueError, match="must be >= 0"):
        List(item=(Int(),), min=Min(n))


def test_list_empty_length_range():
    with pytest.raises(ValueError, match="empty range"):
        List(item=(Int(),), min=Min(3), max=Max(2))


def test_list_item_cannot_be_none_shape():
    with pytest.raises(TypeError, match="item cannot be NoneShape"):
        List(item=(NoneShape(),))


def test_list_item_must_be_shape():
    with pytest.raises(TypeError, match="item must be a non-empty tuple of shapes"):
        List(item=(5,))


def test_enumshape_rejects_non_enum():
    with pytest.raises(TypeError, match="must be an Enum class"):
        EnumShape(cls=int)


def test_enumshape_rejects_flag():
    class Perm(Flag):
        R = 1
        W = 2

    with pytest.raises(TypeError, match="Flag enums are not supported"):
        EnumShape(cls=Perm)


def test_enumshape_rejects_empty_enum():
    class Empty(Enum):
        pass

    with pytest.raises(ValueError, match="enum has no members"):
        EnumShape(cls=Empty)


def test_str_empty_length_range():
    with pytest.raises(ValueError, match="empty range"):
        Str(min=Min(5), max=Max(2))


def test_str_min_exclusive_rejected():
    with pytest.raises(ValueError, match="exclusive bounds are not supported for lengths"):
        Str(min=Min(1, exclusive=True))


def test_str_choice_shorter_than_minimum():
    with pytest.raises(ValueError, match="shorter than minimum"):
        Str(min=Min(3), choices=Choices(values=("ab",)))

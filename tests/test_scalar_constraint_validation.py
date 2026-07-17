from datetime import date, time

import pytest

from pytypehint import Choices, Max, Min, MultipleOf, Pattern
from pytypehint.shapes import Date, Float, Int, Str, Time


def test_float_exclusive_max_rejects_bound():
    with pytest.raises(ValueError, match="too large.*exclusive"):
        Float(max=Max(10.0, exclusive=True))._check(10.0)


def test_float_exclusive_min_rejects_bound():
    with pytest.raises(ValueError, match="too small.*exclusive"):
        Float(min=Min(1.0, exclusive=True))._check(1.0)


def test_float_not_a_choice():
    with pytest.raises(ValueError, match="not a choice"):
        Float(choices=Choices(values=(1.0, 2.0)))._check(3.0)


def test_date_exclusive_max_rejects_bound():
    with pytest.raises(ValueError, match="too late.*exclusive"):
        Date(max=Max(date(2020, 1, 2), exclusive=True))._check(date(2020, 1, 2))


def test_date_inclusive_max_rejects_beyond():
    with pytest.raises(ValueError, match="too late"):
        Date(max=Max(date(2020, 1, 1)))._check(date(2020, 1, 2))


def test_date_not_a_choice():
    with pytest.raises(ValueError, match="not a choice"):
        Date(choices=Choices(values=(date(2020, 1, 1),)))._check(date(2020, 1, 2))


def test_time_check_rejects_non_time_type():
    with pytest.raises(TypeError, match="expected time, got int"):
        Time()._check(5)


def test_time_exclusive_max_rejects_bound():
    with pytest.raises(ValueError, match="too late.*exclusive"):
        Time(max=Max(time(17, 0), exclusive=True))._check(time(17, 0))


def test_time_inclusive_max_rejects_beyond():
    with pytest.raises(ValueError, match="too late"):
        Time(max=Max(time(17, 0)))._check(time(18, 0))


def test_time_not_a_choice():
    with pytest.raises(ValueError, match="not a choice"):
        Time(choices=Choices(values=(time(9, 0),)))._check(time(10, 0))


@pytest.mark.parametrize("v", [-1, -100, 0])
def test_int_exclusive_min_rejects_at_or_below(v):
    with pytest.raises(ValueError, match="too small"):
        Int(min=Min(0, exclusive=True))._check(v)


@pytest.mark.parametrize("v", [10, 11, 100])
def test_int_exclusive_max_rejects_at_or_above(v):
    with pytest.raises(ValueError, match="too large"):
        Int(max=Max(10, exclusive=True))._check(v)


def test_int_exclusive_min_message_mentions_exclusive():
    with pytest.raises(ValueError, match="exclusive"):
        Int(min=Min(0, exclusive=True))._check(0)


def test_int_multiple_of_check():
    shape = Int(multiple_of=MultipleOf(7))
    shape._check(14)
    with pytest.raises(ValueError, match="not a multiple"):
        shape._check(15)


def test_int_not_a_choice_check():
    with pytest.raises(ValueError, match="not a choice"):
        Int(choices=Choices(values=(1, 2, 3)))._check(4)


@pytest.mark.parametrize("s,msg", [
    ("a", "too short"),
    ("", "too short"),
])
def test_str_too_short(s, msg):
    with pytest.raises(ValueError, match=msg):
        Str(min=Min(2))._check(s)


@pytest.mark.parametrize("s", ["abcd", "abcde", "xxxxxxxx"])
def test_str_too_long(s):
    with pytest.raises(ValueError, match="too long"):
        Str(max=Max(3))._check(s)


def test_str_pattern_check_rejects():
    with pytest.raises(ValueError, match="does not match pattern"):
        Str(pattern=Pattern(r"[a-z]+"))._check("ABC")


def test_str_pattern_custom_message_check():
    with pytest.raises(ValueError, match="only digits"):
        Str(pattern=Pattern(r"\d+", message="only digits"))._check("abc")


def test_str_not_a_choice_check():
    with pytest.raises(ValueError, match="not a choice"):
        Str(choices=Choices(values=("a", "b")))._check("c")


@pytest.mark.parametrize("v", [0.0, -0.5, -100.0])
def test_float_inclusive_min_boundary(v):
    shape = Float(min=Min(0.0))
    if v >= 0.0:
        shape._check(v)
    else:
        with pytest.raises(ValueError, match="too small"):
            shape._check(v)


@pytest.mark.parametrize("d", [date(2020, 6, 1), date(2020, 6, 15), date(2020, 7, 1)])
def test_date_inclusive_max_boundary(d):
    shape = Date(max=Max(date(2020, 6, 15)))
    if d <= date(2020, 6, 15):
        shape._check(d)
    else:
        with pytest.raises(ValueError, match="too late"):
            shape._check(d)


def test_date_exclusive_min_rejects_bound():
    with pytest.raises(ValueError, match="exclusive"):
        Date(min=Min(date(2020, 1, 1), exclusive=True))._check(date(2020, 1, 1))


def test_time_exclusive_min_rejects_bound():
    with pytest.raises(ValueError, match="exclusive"):
        Time(min=Min(time(9, 0), exclusive=True))._check(time(9, 0))


@pytest.mark.parametrize("micro", [0, 1, 500000, 999999])
def test_time_microsecond_precision_within_bounds(micro):
    Time(min=Min(time(9, 0, 0, 0)), max=Max(time(9, 0, 1, 0)))._check(time(9, 0, 0, micro))

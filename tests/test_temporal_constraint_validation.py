from datetime import date, time, timedelta

import pytest

from pytypehint import Choices, Max, Min
from pytypehint.shapes import Date, Time


DATE_INCL = Date(min=Min(date(2020, 1, 10)), max=Max(date(2020, 1, 20)))
DATE_EXCL = Date(min=Min(date(2020, 1, 10), exclusive=True),
                 max=Max(date(2020, 1, 20), exclusive=True))


@pytest.mark.parametrize("day", range(10, 21))
def test_date_inclusive_accepts_span(day):
    DATE_INCL._check(date(2020, 1, day))


@pytest.mark.parametrize("day", [1, 5, 9, 21, 25, 31])
def test_date_inclusive_rejects_outside(day):
    with pytest.raises(ValueError):
        DATE_INCL._check(date(2020, 1, day))


@pytest.mark.parametrize("day", range(11, 20))
def test_date_exclusive_accepts_interior(day):
    DATE_EXCL._check(date(2020, 1, day))


@pytest.mark.parametrize("day", [9, 10, 20, 21])
def test_date_exclusive_rejects_ends(day):
    with pytest.raises(ValueError):
        DATE_EXCL._check(date(2020, 1, day))


@pytest.mark.parametrize("day", [1, 15, 30])
def test_date_min_only_rejects_before(day):
    shape = Date(min=Min(date(2020, 6, 15)))
    if date(2020, 6, day) < date(2020, 6, 15):
        with pytest.raises(ValueError, match="too early"):
            shape._check(date(2020, 6, day))
    else:
        shape._check(date(2020, 6, day))


DATE_CHOICES = Date(choices=Choices(values=(
    date(2020, 1, 1), date(2020, 6, 15), date(2020, 12, 31))))


@pytest.mark.parametrize("d", [date(2020, 1, 1), date(2020, 6, 15), date(2020, 12, 31)])
def test_date_choices_accepts_members(d):
    DATE_CHOICES._check(d)


@pytest.mark.parametrize("d", [date(2020, 1, 2), date(2019, 12, 31), date(2021, 1, 1)])
def test_date_choices_rejects_non_members(d):
    with pytest.raises(ValueError, match="not a choice"):
        DATE_CHOICES._check(d)


TIME_INCL = Time(min=Min(time(9, 0)), max=Max(time(17, 0)))
TIME_EXCL = Time(min=Min(time(9, 0), exclusive=True),
                 max=Max(time(17, 0), exclusive=True))


@pytest.mark.parametrize("hour", range(9, 18))
def test_time_inclusive_accepts_span(hour):
    TIME_INCL._check(time(hour, 0))


@pytest.mark.parametrize("hour", [0, 5, 8, 18, 20, 23])
def test_time_inclusive_rejects_outside(hour):
    with pytest.raises(ValueError):
        TIME_INCL._check(time(hour, 0))


@pytest.mark.parametrize("hour", range(10, 17))
def test_time_exclusive_accepts_interior(hour):
    TIME_EXCL._check(time(hour, 0))


@pytest.mark.parametrize("hour", [8, 9, 17, 18])
def test_time_exclusive_rejects_ends(hour):
    with pytest.raises(ValueError):
        TIME_EXCL._check(time(hour, 0))


@pytest.mark.parametrize("minute", [0, 15, 30, 45, 59])
def test_time_minute_granularity_within_bounds(minute):
    Time(min=Min(time(9, 0)), max=Max(time(10, 0)))._check(time(9, minute))


@pytest.mark.parametrize("mm,dd", [(1, 31), (2, 29), (6, 30), (12, 25)])
def test_date_leap_and_month_ends_accepted(mm, dd):
    Date()._check(date(2020, mm, dd))


@pytest.mark.parametrize("month", range(1, 13))
def test_date_all_months_first_day_accepted(month):
    Date()._check(date(2023, month, 1))


@pytest.mark.parametrize("year", [1, 1000, 1970, 2000, 2024, 9999])
def test_date_wide_year_range_accepted(year):
    Date()._check(date(year, 6, 15))


@pytest.mark.parametrize("year", [2020, 2024, 2000, 1600])
def test_date_feb_29_on_leap_years(year):
    Date()._check(date(year, 2, 29))


@pytest.mark.parametrize("d", [date(2020, 6, 30), date(2020, 7, 1)])
def test_date_exclusive_min_only_boundary(d):
    shape = Date(min=Min(date(2020, 6, 30), exclusive=True))
    if d > date(2020, 6, 30):
        shape._check(d)
    else:
        with pytest.raises(ValueError, match="exclusive"):
            shape._check(d)


@pytest.mark.parametrize("year", [2019, 2021, 2100])
def test_date_across_year_boundary(year):
    shape = Date(min=Min(date(2020, 1, 1)), max=Max(date(2020, 12, 31)))
    with pytest.raises(ValueError):
        shape._check(date(year, 6, 1))


@pytest.mark.parametrize("second", [0, 1, 30, 59])
def test_time_second_granularity(second):
    Time(min=Min(time(9, 0, 0)), max=Max(time(9, 1, 0)))._check(time(9, 0, second))


@pytest.mark.parametrize("hour", range(0, 24))
def test_time_full_day_no_bounds(hour):
    Time()._check(time(hour, 0))


@pytest.mark.parametrize("t", [time(0, 0), time(12, 0), time(23, 59, 59)])
def test_time_extremes_accepted(t):
    Time()._check(t)


TIME_CHOICES = Time(choices=Choices(values=(time(9, 0), time(12, 30), time(17, 45))))


@pytest.mark.parametrize("t", [time(9, 0), time(12, 30), time(17, 45)])
def test_time_choices_accept(t):
    TIME_CHOICES._check(t)


@pytest.mark.parametrize("t", [time(9, 1), time(0, 0), time(23, 0)])
def test_time_choices_reject(t):
    with pytest.raises(ValueError, match="not a choice"):
        TIME_CHOICES._check(t)


@pytest.mark.parametrize("span", [1, 2, 3, 7, 30, 365])
def test_date_span_widths_compile(span):
    Date(min=Min(date(2020, 1, 1)), max=Max(date(2020, 1, 1) + timedelta(days=span)))

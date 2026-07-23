from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Annotated

import pytest

from pytypehint.atoms import Choices, Max, Min, Pattern, Placeholder, Slider, Step
from pytypehint.bridge import struct_of
from pytypehint.shapes import Date, Int, Time


def test_min_accepts_date():
    Min(date(2020, 1, 1))


def test_min_accepts_time():
    Min(time(9, 0))


def test_min_rejects_datetime():
    with pytest.raises(TypeError, match="must be orderable"):
        Min(datetime(2020, 1, 1))


def test_step_rejects_date():
    with pytest.raises(TypeError, match="must be a number"):
        Step(date(2020, 1, 1))


def test_int_min_rejects_date():
    with pytest.raises(TypeError, match="expected int, got date"):
        Int(min=Min(date(2020, 1, 1)))


def test_date_min_rejects_int():
    with pytest.raises(TypeError, match="expected date, got int"):
        Date(min=Min(0))


def test_date_min_rejects_time():
    with pytest.raises(TypeError, match="expected date, got time"):
        Date(min=Min(time(9, 0)))


def test_time_min_rejects_float():
    with pytest.raises(TypeError, match="expected time, got float"):
        Time(min=Min(0.5))


def test_date_check_accepts_date():
    Date()._check(date(2020, 1, 1))


def test_date_check_rejects_datetime():
    with pytest.raises(TypeError, match="expected date, got datetime"):
        Date()._check(datetime(2020, 1, 1))


def test_date_check_rejects_str():
    with pytest.raises(TypeError, match="expected date, got str"):
        Date()._check("2020-01-01")


def test_date_too_early():
    with pytest.raises(ValueError, match="too early"):
        Date(min=Min(date(2020, 1, 1)))._check(date(2019, 12, 31))


def test_date_exclusive_min_rejects_bound():
    with pytest.raises(ValueError, match="exclusive"):
        Date(min=Min(date(2020, 1, 1), exclusive=True))._check(date(2020, 1, 1))


def test_date_too_late():
    with pytest.raises(ValueError, match="too late"):
        Date(max=Max(date(2020, 1, 1)))._check(date(2020, 1, 2))


def test_date_discrete_empty_range():
    with pytest.raises(ValueError, match="empty range"):
        Date(min=Min(date(2020, 1, 1), exclusive=True),
             max=Max(date(2020, 1, 2), exclusive=True))


def test_date_two_day_span_one_exclusive_compiles():
    Date(min=Min(date(2020, 1, 1), exclusive=True),
         max=Max(date(2020, 1, 3), exclusive=True))


def test_time_check_accepts_time():
    Time()._check(time(9, 0))


def test_time_check_rejects_aware():
    with pytest.raises(ValueError, match="must be naive"):
        Time()._check(time(9, 0, tzinfo=timezone.utc))


def test_time_naive_check_before_comparison():
    with pytest.raises(ValueError, match="must be naive"):
        Time(min=Min(time(8, 0)))._check(time(9, 0, tzinfo=timezone.utc))


def test_time_too_early_inclusive():
    with pytest.raises(ValueError, match="too early"):
        Time(min=Min(time(9, 0)))._check(time(8, 0))


def test_time_too_early_exclusive():
    with pytest.raises(ValueError, match="exclusive"):
        Time(min=Min(time(9, 0), exclusive=True))._check(time(9, 0))


def test_time_too_late_inclusive():
    with pytest.raises(ValueError, match="too late"):
        Time(max=Max(time(17, 0)))._check(time(18, 0))


def test_time_too_late_exclusive():
    with pytest.raises(ValueError, match="exclusive"):
        Time(max=Max(time(17, 0), exclusive=True))._check(time(17, 0))


def test_time_midnight_range_is_empty():
    with pytest.raises(ValueError, match="empty range"):
        Time(min=Min(time(22, 0)), max=Max(time(6, 0)))


def test_time_forward_range_compiles():
    Time(min=Min(time(6, 0)), max=Max(time(22, 0)))


def test_time_single_instant_range_compiles():
    Time(min=Min(time(9, 0)), max=Max(time(9, 0)))


def test_time_single_instant_min_exclusive_empty():
    with pytest.raises(ValueError, match="empty range"):
        Time(min=Min(time(9, 0), exclusive=True), max=Max(time(9, 0)))


def test_time_single_instant_max_exclusive_empty():
    with pytest.raises(ValueError, match="empty range"):
        Time(min=Min(time(9, 0)), max=Max(time(9, 0), exclusive=True))


def test_date_choices_reject_int():
    with pytest.raises(TypeError, match="expected date, got int"):
        Date(choices=Choices(values=(0,)))


def test_date_choices_below_minimum():
    with pytest.raises(ValueError, match="below minimum"):
        Date(min=Min(date(2020, 1, 1)), choices=Choices(values=(date(2019, 1, 1),)))


def test_time_choices_reject_aware():
    with pytest.raises(ValueError, match="must be naive"):
        Time(choices=Choices(values=(time(9, 0, tzinfo=timezone.utc),)))


def _one_field(annotation, default):
    @dataclass
    class Model:
        x: annotation = default
    return Model


def test_date_step_metadata_rejected():
    with pytest.raises(TypeError, match="unsupported metadata"):
        struct_of(_one_field(Annotated[date, Step(1)], date(2020, 1, 1)))


def test_time_slider_metadata_rejected():
    with pytest.raises(TypeError, match="unsupported metadata"):
        struct_of(_one_field(Annotated[time, Slider()], time(9, 0)))


def test_date_pattern_metadata_rejected():
    with pytest.raises(TypeError, match="unsupported metadata"):
        struct_of(_one_field(Annotated[date, Pattern("x")], date(2020, 1, 1)))


def test_date_placeholder_metadata_compiles():
    struct_of(_one_field(Annotated[date, Placeholder("pick")], date(2020, 1, 1)))


def test_bridge_date_bound_resolves():
    s = struct_of(_one_field(Annotated[date, Min(date(2020, 1, 1))], date(2021, 1, 1)))
    assert s.resolve({"x": date(2021, 1, 1)}) == {"x": date(2021, 1, 1)}


def test_bridge_date_bound_rejects_early():
    s = struct_of(_one_field(Annotated[date, Min(date(2020, 1, 1))], date(2021, 1, 1)))
    with pytest.raises(ValueError, match="too early"):
        s.resolve({"x": date(2019, 1, 1)})


def test_bridge_date_rejects_datetime():
    s = struct_of(_one_field(Annotated[date, Min(date(2020, 1, 1))], date(2021, 1, 1)))
    with pytest.raises(TypeError, match="expected date, got datetime"):
        s.resolve({"x": datetime(2021, 1, 1)})


def test_bridge_date_rejects_str():
    s = struct_of(_one_field(Annotated[date, Min(date(2020, 1, 1))], date(2021, 1, 1)))
    with pytest.raises(TypeError, match="expected date, got str"):
        s.resolve({"x": "2021-01-01"})


def test_bridge_date_optional_compiles():
    struct_of(_one_field(date | None, None))


def test_bridge_list_of_time_compiles():
    @dataclass
    class Model:
        x: list[time] = field(default_factory=list)

    s = struct_of(Model)
    assert s.resolve({"x": [time(9, 0)]}) == {"x": [time(9, 0)]}


def test_bridge_date_time_union_routes():
    s = struct_of(_one_field(date | time, date(2020, 1, 1)))
    assert s.resolve({"x": time(9, 0)}) == {"x": time(9, 0)}
    assert s.resolve({"x": date(2020, 1, 1)}) == {"x": date(2020, 1, 1)}


def test_bridge_datetime_field_unsupported():
    with pytest.raises(TypeError, match="unsupported type"):
        struct_of(_one_field(datetime, datetime(2020, 1, 1)))


_REF_DATE = date(2020, 1, 1)


def test_struct_date_default_by_reference():
    @dataclass
    class Model:
        d: date = _REF_DATE

    assert struct_of(Model).resolve({})["d"] is _REF_DATE


def test_struct_datetime_default_fails():
    @dataclass
    class Model:
        d: date = datetime(2020, 1, 1)

    with pytest.raises(TypeError, match="expected date, got datetime"):
        struct_of(Model)


def test_date_min_exclusive_at_max_edge_rejected():
    with pytest.raises(ValueError, match="exclusive bound at 9999-12-31 leaves no valid date"):
        Date(min=Min(date.max, exclusive=True))


def test_date_max_exclusive_at_min_edge_rejected():
    with pytest.raises(ValueError, match="exclusive bound at 0001-01-01 leaves no valid date"):
        Date(max=Max(date.min, exclusive=True))


def test_date_min_inclusive_at_max_edge_compiles():
    Date(min=Min(date.max))


def test_time_min_exclusive_at_max_edge_rejected():
    with pytest.raises(ValueError,
                       match="exclusive bound at 23:59:59 leaves no valid time"):
        Time(min=Min(time(23, 59, 59), exclusive=True))


def test_time_max_exclusive_at_min_edge_rejected():
    with pytest.raises(ValueError,
                       match="exclusive bound at 00:00:00 leaves no valid time"):
        Time(max=Max(time.min, exclusive=True))


def test_time_min_inclusive_at_max_edge_compiles():
    Time(min=Min(time(23, 59, 59)))


def test_time_max_with_microseconds_rejected():
    with pytest.raises(ValueError, match="whole seconds"):
        Time(min=Min(time.max))

"""Time precision is limited to whole seconds (pytypehint 0.0.6).

A `datetime.time` value is admissible only when its `microsecond` is zero. This
holds at every entry point of the core: shape bounds and choices at compile time,
and every path a value can travel at runtime — direct validation, defaults,
`resolve`, `build`, nested dataclasses, unions and lists — all funnel through the
one `Time._check`. The structured error carries the offending coordinate as
`path`, exactly like every other constraint.
"""

from dataclasses import dataclass, field
from datetime import time
from typing import Annotated

import pytest

from pytypehint import (
    Choices, Max, Min, SchemaValueError, struct_of,
)
from pytypehint.shapes import Time


SUBSECOND = time(12, 30, 0, 500000)
WHOLE = time(12, 30, 0)


# --- direct validation ------------------------------------------------------

def test_direct_check_accepts_whole_second():
    Time()._check(WHOLE)


@pytest.mark.parametrize("t", [time(0, 0, 0, 1), SUBSECOND, time(23, 59, 59, 999999)])
def test_direct_check_rejects_subsecond(t):
    with pytest.raises(ValueError, match="whole seconds"):
        Time()._check(t)


# --- constraints: min / max -------------------------------------------------

def test_min_rejects_subsecond_bound():
    with pytest.raises(ValueError, match="min: time precision is limited to whole seconds"):
        Time(min=Min(SUBSECOND))


def test_max_rejects_subsecond_bound():
    with pytest.raises(ValueError, match="max: time precision is limited to whole seconds"):
        Time(max=Max(SUBSECOND))


def test_whole_second_bounds_compile():
    Time(min=Min(time(9, 0, 0)), max=Max(time(17, 0, 0)))


# --- constraints: choices ---------------------------------------------------

def test_choices_reject_subsecond_member():
    with pytest.raises(ValueError, match="choices: time precision is limited to whole seconds"):
        Time(choices=Choices(values=(time(9, 0, 0), SUBSECOND)))


def test_choices_accept_whole_seconds():
    Time(choices=Choices(values=(time(9, 0, 0), time(17, 30, 0))))


# --- defaults (compile-time certification) ----------------------------------

def test_default_subsecond_rejected_with_path():
    @dataclass
    class Model:
        t: time = SUBSECOND

    with pytest.raises(SchemaValueError, match="whole seconds") as exc:
        struct_of(Model)
    assert exc.value.path == ("t", "default")


def test_default_whole_second_compiles():
    @dataclass
    class Model:
        t: time = WHOLE

    assert struct_of(Model).resolve({})["t"] == WHOLE


# --- resolve / build --------------------------------------------------------

def _model():
    @dataclass
    class Model:
        t: time = WHOLE
    return struct_of(Model)


def test_resolve_rejects_subsecond_with_path():
    with pytest.raises(SchemaValueError, match="whole seconds") as exc:
        _model().resolve({"t": SUBSECOND})
    assert exc.value.path == ("t",)


def test_build_rejects_subsecond_with_path():
    with pytest.raises(SchemaValueError, match="whole seconds") as exc:
        _model().build({"t": SUBSECOND})
    assert exc.value.path == ("t",)


def test_build_accepts_whole_second():
    built = _model().build({"t": WHOLE})
    assert built.t == WHOLE


# --- nested dataclass -------------------------------------------------------

def test_nested_dataclass_reports_full_path():
    @dataclass
    class Inner:
        t: time = WHOLE

    @dataclass
    class Outer:
        inner: Inner = field(default_factory=Inner)

    schema = struct_of(Outer)
    with pytest.raises(SchemaValueError, match="whole seconds") as exc:
        schema.build({"inner": {"t": SUBSECOND}})
    assert exc.value.path == ("inner", "t")


# --- union ------------------------------------------------------------------

def test_union_rejects_subsecond_time():
    @dataclass
    class Model:
        t: int | time = 0

    schema = struct_of(Model)
    schema.resolve({"t": WHOLE})  # the time branch accepts whole seconds
    with pytest.raises(SchemaValueError, match="whole seconds") as exc:
        schema.resolve({"t": SUBSECOND})
    assert exc.value.path == ("t",)


# --- list -------------------------------------------------------------------

def test_list_reports_item_index():
    @dataclass
    class Model:
        times: list[time] = field(default_factory=list)

    schema = struct_of(Model)
    schema.resolve({"times": [WHOLE, time(8, 0, 0)]})
    with pytest.raises(SchemaValueError, match="whole seconds") as exc:
        schema.resolve({"times": [WHOLE, SUBSECOND]})
    assert exc.value.path == ("times", 1)

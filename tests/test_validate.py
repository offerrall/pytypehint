from dataclasses import dataclass, field
from datetime import date, time, datetime, timezone
from typing import Annotated

import pytest

from pytypehint import (
    Choices, Max, Min, MultipleOf, Pattern, struct_of,
)
from pytypehint.shapes import (
    Bool, Date, Float, Int, List, NoneShape, Str, Time,
)


# --------------------------------------------------------------------------
# Type validation: exact type, wrong type raises TypeError
# --------------------------------------------------------------------------

TYPE_OK = [
    (Int(), 7),
    (Float(), 7.0),
    (Str(), "x"),
    (Bool(), True),
    (Bool(), False),
    (Date(), date(2020, 1, 1)),
    (Time(), time(9, 0)),
    (NoneShape(), None),
]


@pytest.mark.parametrize("shape,value", TYPE_OK)
def test_valid_type_passes(shape, value):
    shape._check(value)


TYPE_BAD = [
    (Int(), 1.0, "expected int"),
    (Int(), True, "expected int"),
    (Float(), 1, "expected float"),
    (Str(), 1, "expected str"),
    (Bool(), 1, "expected bool"),
    (Date(), datetime(2020, 1, 1), "expected date"),
    (Time(), 5, "expected time"),
    (NoneShape(), 0, "expected None"),
]


@pytest.mark.parametrize("shape,value,msg", TYPE_BAD)
def test_wrong_type_raises_typeerror(shape, value, msg):
    with pytest.raises(TypeError, match=msg):
        shape._check(value)


# --------------------------------------------------------------------------
# Constraint validation: right type, out of bounds raises ValueError
# --------------------------------------------------------------------------

CONSTRAINT_BAD = [
    (Int(min=Min(0)), -1, "too small"),
    (Int(max=Max(10)), 11, "too large"),
    (Int(multiple_of=MultipleOf(3)), 4, "not a multiple"),
    (Int(choices=Choices(values=(1, 2))), 3, "not a choice"),
    (Float(min=Min(0.0)), -0.5, "too small"),
    (Float(max=Max(1.0)), 1.5, "too large"),
    (Str(min=Min(3)), "ab", "too short"),
    (Str(max=Max(3)), "abcd", "too long"),
    (Str(pattern=Pattern(r"\d+")), "abc", "does not match pattern"),
    (Date(min=Min(date(2020, 1, 1))), date(2019, 1, 1), "too early"),
    (Date(max=Max(date(2020, 1, 1))), date(2021, 1, 1), "too late"),
    (Time(min=Min(time(9, 0))), time(8, 0), "too early"),
    (Time(max=Max(time(17, 0))), time(18, 0), "too late"),
]


@pytest.mark.parametrize("shape,value,msg", CONSTRAINT_BAD)
def test_constraint_violation_raises_valueerror(shape, value, msg):
    with pytest.raises(ValueError, match=msg):
        shape._check(value)


def test_type_error_precedes_constraint_error():
    with pytest.raises(TypeError, match="expected int"):
        Int(min=Min(0))._check("not an int")


def test_float_finiteness_is_a_constraint_not_a_type():
    with pytest.raises(ValueError, match="not finite"):
        Float()._check(float("nan"))


def test_time_naive_check_before_bound_comparison():
    with pytest.raises(ValueError, match="must be naive"):
        Time(min=Min(time(8, 0)))._check(time(9, 0, tzinfo=timezone.utc))


# --------------------------------------------------------------------------
# Exclusive bounds at validation time
# --------------------------------------------------------------------------

@pytest.mark.parametrize("shape,bound", [
    (Int(min=Min(0, exclusive=True)), 0),
    (Int(max=Max(10, exclusive=True)), 10),
    (Float(min=Min(0.0, exclusive=True)), 0.0),
    (Float(max=Max(1.0, exclusive=True)), 1.0),
    (Date(min=Min(date(2020, 1, 1), exclusive=True)), date(2020, 1, 1)),
    (Time(max=Max(time(17, 0), exclusive=True)), time(17, 0)),
])
def test_exclusive_bound_rejects_the_bound_itself(shape, bound):
    with pytest.raises(ValueError, match="exclusive"):
        shape._check(bound)


# --------------------------------------------------------------------------
# Validation through resolve mirrors direct check
# --------------------------------------------------------------------------

@dataclass
class Person:
    name: Annotated[str, Min(1)] = "x"
    age: Annotated[int, Min(0), Max(150)] = 0


def test_resolve_accepts_valid_record():
    data = {"name": "Ada", "age": 36}
    assert struct_of(Person).resolve(data) == data


@pytest.mark.parametrize("data,exc,msg", [
    ({"name": "", "age": 36}, ValueError, "name: too short"),
    ({"name": "Ada", "age": -1}, ValueError, "age: too small"),
    ({"name": "Ada", "age": 999}, ValueError, "age: too large"),
    ({"name": 5, "age": 36}, TypeError, "name: expected str"),
    ({"name": "Ada", "age": "old"}, TypeError, "age: expected int"),
])
def test_resolve_reports_field_and_reason(data, exc, msg):
    with pytest.raises(exc, match=msg):
        struct_of(Person).resolve(data)


# --------------------------------------------------------------------------
# check(instance): validate an already-built object
# --------------------------------------------------------------------------

@dataclass
class Point:
    x: int = 0
    y: int = 0


def test_check_instance_passes():
    struct_of(Point)._check(Point(1, 2))


def test_check_instance_wrong_top_type():
    with pytest.raises(TypeError, match="expected Point, got str"):
        struct_of(Point)._check("nope")


def test_check_instance_bad_field():
    with pytest.raises(TypeError, match="y: expected int, got str"):
        struct_of(Point)._check(Point(1, "a"))


# --------------------------------------------------------------------------
# Nested error paths: the failure path is spelled out
# --------------------------------------------------------------------------

@dataclass
class Segment:
    start: Point = field(default_factory=Point)
    end: Point = field(default_factory=Point)


def test_nested_instance_path():
    with pytest.raises(TypeError, match="end: y: expected int, got str"):
        struct_of(Segment)._check(Segment(end=Point(1, "a")))


def test_nested_dict_path_via_resolve():
    with pytest.raises(TypeError, match="start: x: expected int, got str"):
        struct_of(Segment).resolve({"start": {"x": "bad", "y": 0}})


@dataclass
class Bag:
    items: list[Annotated[int, Min(0)]] = field(default_factory=list)


def test_list_item_index_in_path():
    with pytest.raises(ValueError, match=r"items: \[2\]: too small"):
        struct_of(Bag).resolve({"items": [0, 1, -5, 3]})


def test_list_item_wrong_type_index_in_path():
    with pytest.raises(TypeError, match=r"items: \[1\]: expected int"):
        struct_of(Bag).resolve({"items": [0, "x"]})


@dataclass
class Matrix:
    rows: list[list[Annotated[int, Min(0)]]] = field(default_factory=list)


def test_doubly_nested_list_path():
    with pytest.raises(ValueError, match=r"rows: \[1\]: \[0\]: too small"):
        struct_of(Matrix).resolve({"rows": [[1, 2], [-3, 4]]})


# --------------------------------------------------------------------------
# Validation never mutates and never transforms the value
# --------------------------------------------------------------------------

def test_valid_value_passes_by_reference():
    payload = [0, 1, 2]

    @dataclass
    class M:
        xs: list[int] = field(default_factory=list)

    out = struct_of(M).resolve({"xs": payload})
    assert out["xs"] is payload


def test_list_check_does_not_alter_contents():
    payload = [3, 1, 2]
    List(item=(Int(),))._check(payload)
    assert payload == [3, 1, 2]


# --------------------------------------------------------------------------
# Boundary acceptance sweeps: the inclusive bound value is valid
# --------------------------------------------------------------------------

@pytest.mark.parametrize("shape,value", [
    (Int(min=Min(0)), 0),
    (Int(max=Max(0)), 0),
    (Int(min=Min(-5), max=Max(5)), -5),
    (Int(min=Min(-5), max=Max(5)), 5),
    (Float(min=Min(0.0)), 0.0),
    (Float(max=Max(1.0)), 1.0),
    (Str(min=Min(0)), ""),
    (Str(min=Min(2), max=Max(2)), "ab"),
    (Date(min=Min(date(2020, 1, 1))), date(2020, 1, 1)),
    (Date(max=Max(date(2020, 1, 1))), date(2020, 1, 1)),
    (Time(min=Min(time(9, 0))), time(9, 0)),
    (Time(max=Max(time(9, 0))), time(9, 0)),
])
def test_inclusive_bound_value_is_accepted(shape, value):
    shape._check(value)


# --------------------------------------------------------------------------
# Every error is exactly TypeError or ValueError, never anything else
# --------------------------------------------------------------------------

@pytest.mark.parametrize("shape,value", [
    (Int(), "x"),
    (Int(min=Min(0)), -1),
    (Str(pattern=Pattern(r"\d+")), "x"),
    (Float(), float("nan")),
    (Date(), 5),
    (Time(), time(9, 0, tzinfo=timezone.utc)),
])
def test_only_type_or_value_errors(shape, value):
    with pytest.raises((TypeError, ValueError)):
        shape._check(value)


# --------------------------------------------------------------------------
# resolve and check agree on validity for the same value
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value,valid", [
    (5, True), (-1, False), (150, True), (151, False), ("x", False),
])
def test_resolve_and_check_agree(value, valid):
    @dataclass
    class Age:
        v: Annotated[int, Min(0), Max(150)] = 0

    schema = struct_of(Age)
    if valid:
        assert schema.resolve({"v": value}) == {"v": value}
    else:
        with pytest.raises((TypeError, ValueError)):
            schema.resolve({"v": value})


# --------------------------------------------------------------------------
# Deep path grammar at several nesting levels
# --------------------------------------------------------------------------

@dataclass
class L3:
    v: Annotated[int, Min(0)] = 0


@dataclass
class L2:
    inner: L3 = field(default_factory=L3)


@dataclass
class L1:
    mid: L2 = field(default_factory=L2)


def test_three_level_nested_path():
    with pytest.raises(ValueError, match="mid: inner: v: too small"):
        struct_of(L1).resolve({"mid": {"inner": {"v": -1}}})


@dataclass
class ListOfStructs:
    rows: list[L3] = field(default_factory=list)


@pytest.mark.parametrize("idx", range(0, 4))
def test_list_of_structs_path(idx):
    rows = [{"v": 0} for _ in range(4)]
    rows[idx] = {"v": -9}
    with pytest.raises(ValueError, match=rf"rows: \[{idx}\]: v: too small"):
        struct_of(ListOfStructs).resolve({"rows": rows})

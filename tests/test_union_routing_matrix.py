import itertools
from dataclasses import dataclass, field, make_dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Annotated, Literal, Union

import pytest

from pytypehint import Max, Min, signature_of, struct_of


SCALARS = [int, float, str, bool, date, time]
REP = {
    int: 7,
    float: 2.5,
    str: "hello",
    bool: True,
    date: date(2021, 3, 4),
    time: time(11, 22),
}


def union_schema(types, default):
    ann = Union[tuple(types)]
    M = make_dataclass("M", [("v", ann, field(default=default))])
    return struct_of(M)


def resolve_v(schema, value):
    return schema.resolve({"v": value})["v"]


# --------------------------------------------------------------------------
# Brute force: every ordered pair of distinct scalar arms
# --------------------------------------------------------------------------

PAIRS = [(a, b) for a in SCALARS for b in SCALARS if a is not b]


@pytest.mark.parametrize("a,b", PAIRS, ids=[f"{a.__name__}|{b.__name__}" for a, b in PAIRS])
def test_pair_routes_first_arm(a, b):
    schema = union_schema([a, b], REP[a])
    assert resolve_v(schema, REP[a]) == REP[a]


@pytest.mark.parametrize("a,b", PAIRS, ids=[f"{a.__name__}|{b.__name__}" for a, b in PAIRS])
def test_pair_routes_second_arm(a, b):
    schema = union_schema([a, b], REP[a])
    assert resolve_v(schema, REP[b]) == REP[b]


@pytest.mark.parametrize("a,b", PAIRS, ids=[f"{a.__name__}|{b.__name__}" for a, b in PAIRS])
def test_pair_rejects_foreign_type(a, b):
    schema = union_schema([a, b], REP[a])
    foreign = next(t for t in SCALARS if t not in (a, b))
    with pytest.raises(TypeError):
        schema.resolve({"v": REP[foreign]})


# --------------------------------------------------------------------------
# bool never crosses with int, in both orders
# --------------------------------------------------------------------------

@pytest.mark.parametrize("types", [[int, str], [str, int]])
def test_bool_rejected_by_int_str_union(types):
    schema = union_schema(types, REP[int])
    with pytest.raises(TypeError):
        schema.resolve({"v": True})


@pytest.mark.parametrize("types", [[bool, str], [str, bool]])
def test_int_rejected_by_bool_str_union(types):
    schema = union_schema(types, True)
    with pytest.raises(TypeError):
        schema.resolve({"v": 1})


def test_bool_int_union_keeps_arms_separate():
    schema = union_schema([bool, int], True)
    assert resolve_v(schema, True) is True
    assert resolve_v(schema, 5) == 5


# --------------------------------------------------------------------------
# Optionality with many arms: None routes regardless of arm count
# --------------------------------------------------------------------------

@pytest.mark.parametrize("k", range(1, len(SCALARS) + 1))
def test_optional_of_growing_union(k):
    types = SCALARS[:k] + [type(None)]
    schema = union_schema(types, None)
    assert resolve_v(schema, None) is None
    for t in SCALARS[:k]:
        assert resolve_v(schema, REP[t]) == REP[t]


# --------------------------------------------------------------------------
# Order independence: all permutations route the same
# --------------------------------------------------------------------------

@pytest.mark.parametrize("perm", list(itertools.permutations([int, str, type(None)])))
def test_three_way_permutations_route_identically(perm):
    schema = union_schema(list(perm), None)
    assert resolve_v(schema, 7) == 7
    assert resolve_v(schema, "x") == "x"
    assert resolve_v(schema, None) is None


# --------------------------------------------------------------------------
# The full seven-arm union of every scalar plus None
# --------------------------------------------------------------------------

@dataclass
class Everything:
    v: int | float | str | bool | date | time | None = None


@pytest.mark.parametrize("value", [
    7, 2.5, "hello", True, False, date(2020, 1, 1), time(9, 0), None,
])
def test_seven_way_union_routes_every_scalar(value):
    assert struct_of(Everything).resolve({"v": value}) == {"v": value}


@pytest.mark.parametrize("value", [b"x", [], (), {}, 1j, object()])
def test_seven_way_union_rejects_foreign(value):
    with pytest.raises(TypeError, match="expected int"):
        struct_of(Everything).resolve({"v": value})


# --------------------------------------------------------------------------
# Default may sit in any arm of a big union
# --------------------------------------------------------------------------

@pytest.mark.parametrize("t", SCALARS)
def test_default_in_any_arm(t):
    schema = union_schema(SCALARS, REP[t])
    assert schema.resolve({}) == {"v": REP[t]}


@pytest.mark.parametrize("bad", [b"x", [1], (1,), 1j])
def test_default_outside_all_arms_rejected(bad):
    with pytest.raises((TypeError, ValueError)):
        union_schema([int, str], bad)


# --------------------------------------------------------------------------
# Numeric arms stay distinct: int never a float, float never an int
# --------------------------------------------------------------------------

def test_int_float_union_no_widening():
    schema = union_schema([int, float], 0)
    assert resolve_v(schema, 5) == 5
    assert isinstance(resolve_v(schema, 5), int)
    assert resolve_v(schema, 5.0) == 5.0
    assert isinstance(resolve_v(schema, 5.0), float)


# --------------------------------------------------------------------------
# Constraints live per arm, independently
# --------------------------------------------------------------------------

@dataclass
class TwoConstrained:
    v: Annotated[int, Min(0), Max(10)] | Annotated[str, Min(3)] = 0


@pytest.mark.parametrize("value", [0, 5, 10, "abc", "abcdef"])
def test_two_constrained_arms_accept(value):
    assert struct_of(TwoConstrained).resolve({"v": value}) == {"v": value}


@pytest.mark.parametrize("value,msg", [
    (-1, "too small"),
    (11, "too large"),
    ("ab", "too short"),
])
def test_two_constrained_arms_reject(value, msg):
    with pytest.raises(ValueError, match=msg):
        struct_of(TwoConstrained).resolve({"v": value})


# --------------------------------------------------------------------------
# Literal arm inside a union
# --------------------------------------------------------------------------

@dataclass
class LiteralUnion:
    v: Literal["a", "b"] | int = 0


def test_literal_union_accepts_literal_member():
    assert struct_of(LiteralUnion).resolve({"v": "a"}) == {"v": "a"}


def test_literal_union_accepts_int_arm():
    assert struct_of(LiteralUnion).resolve({"v": 99}) == {"v": 99}


def test_literal_union_rejects_non_member_string():
    with pytest.raises(ValueError, match="not a choice"):
        struct_of(LiteralUnion).resolve({"v": "c"})


# --------------------------------------------------------------------------
# Two enums in a union route by identity
# --------------------------------------------------------------------------

class Fruit(Enum):
    APPLE = 1


class Veg(Enum):
    CARROT = 1


@dataclass
class TwoEnums:
    v: Fruit | Veg = Fruit.APPLE


def test_two_enum_union_routes_each():
    assert struct_of(TwoEnums).resolve({"v": Fruit.APPLE}) == {"v": Fruit.APPLE}
    assert struct_of(TwoEnums).resolve({"v": Veg.CARROT}) == {"v": Veg.CARROT}


def test_two_enum_union_rejects_raw_value():
    with pytest.raises(TypeError, match="expected Fruit"):
        struct_of(TwoEnums).resolve({"v": 1})


# --------------------------------------------------------------------------
# Union with list arms
# --------------------------------------------------------------------------

@dataclass
class ListOrInt:
    v: list[int] | int = 0


def test_list_or_int_routes_list():
    assert struct_of(ListOrInt).resolve({"v": [1, 2, 3]}) == {"v": [1, 2, 3]}


def test_list_or_int_routes_int():
    assert struct_of(ListOrInt).resolve({"v": 5}) == {"v": 5}


@dataclass
class OptList:
    v: list[int] | None = None


def test_optional_list_accepts_list_and_none():
    assert struct_of(OptList).resolve({"v": [1, 2]}) == {"v": [1, 2]}
    assert struct_of(OptList).resolve({"v": None}) == {"v": None}


def test_two_list_arms_are_duplicate_types():
    @dataclass
    class M:
        v: list[int] | list[str] = None

    with pytest.raises(ValueError, match="duplicate option types in shape"):
        struct_of(M)


# --------------------------------------------------------------------------
# Dataclass arms: instances, dicts, subclasses
# --------------------------------------------------------------------------

@dataclass
class Inner:
    n: int = 0


@dataclass
class StructOrNone:
    v: Inner | None = None


def test_single_struct_union_accepts_dict():
    assert struct_of(StructOrNone).resolve({"v": {"n": 3}}) == {"v": {"n": 3}}


def test_single_struct_union_accepts_none():
    assert struct_of(StructOrNone).resolve({"v": None}) == {"v": None}


def test_single_struct_union_rejects_instance():
    inner = Inner(n=9)
    with pytest.raises(TypeError, match="v: expected dict, got Inner instance"):
        struct_of(StructOrNone).resolve({"v": inner})


@dataclass
class Base:
    x: int = 0


class Derived(Base):
    pass


@dataclass
class BaseOrInt:
    v: Base | int = 0


def test_union_rejects_subclass_instance():
    with pytest.raises(TypeError, match=r"expected Base \| int, got Derived"):
        struct_of(BaseOrInt).resolve({"v": Derived(x=1)})


# --------------------------------------------------------------------------
# Unions in function signatures behave the same
# --------------------------------------------------------------------------

def test_signature_union_routes_and_defaults():
    def fn(a: int | str = 0):
        ...

    sig = signature_of(fn)
    assert sig.resolve({"a": 5}) == {"a": 5}
    assert sig.resolve({"a": "x"}) == {"a": "x"}
    assert sig.resolve({}) == {"a": 0}
    with pytest.raises(TypeError, match=r"a: expected int \| str, got float"):
        sig.resolve({"a": 1.5})


# --------------------------------------------------------------------------
# Unsupported members inside a union fail at compile time
# --------------------------------------------------------------------------

def test_datetime_arm_is_unsupported():
    @dataclass
    class M:
        v: date | datetime = date(2020, 1, 1)

    with pytest.raises(TypeError, match="unsupported type"):
        struct_of(M)


def test_dict_arm_is_unsupported():
    @dataclass
    class M:
        v: "int | dict" = 0

    with pytest.raises(TypeError, match="unsupported type"):
        struct_of(M)


# --------------------------------------------------------------------------
# Stress: unions nested through lists and dataclasses
# --------------------------------------------------------------------------

@dataclass
class Cell:
    value: int | str | None = None


@dataclass
class Grid:
    cells: list[Cell] = field(default_factory=list)
    fallback: Cell | int = 0


def test_nested_union_grid_resolves_mixed_values():
    data = {
        "cells": [{"value": 1}, {"value": "x"}, {"value": None}],
        "fallback": {"value": 7},
    }
    assert struct_of(Grid).resolve(data) == data


def test_nested_union_grid_reports_deep_failure():
    data = {"cells": [{"value": 1}, {"value": 1.5}], "fallback": 0}
    with pytest.raises(TypeError, match=r"cells: \[1\]: value: expected int \| str \| NoneType, got float"):
        struct_of(Grid).resolve(data)


@dataclass
class Tree:
    tag: int | str = 0
    kids: "list[Tree] | None" = None


@pytest.mark.parametrize("tag", [0, "root"])
def test_recursive_union_tree(tag):
    data = {"tag": tag, "kids": [{"tag": 1, "kids": None}, {"tag": "leaf", "kids": None}]}
    out = struct_of(Tree).resolve(data)
    assert out["tag"] == tag
    assert out["kids"][1]["tag"] == "leaf"

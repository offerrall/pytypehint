from dataclasses import dataclass, field
from datetime import date, time
from typing import Annotated

import pytest

from pytypehint import Max as _Max, Min, Min as _Min, struct_of
from pytypehint.shapes import Int, List, Str


@dataclass
class UInt:
    v: int | str = 0


@dataclass
class UTriple:
    v: int | str | None = 0


@dataclass
class UDateTime:
    v: date | time = date(2020, 1, 1)


@pytest.mark.parametrize("value", [0, 42, -7, 2 ** 40])
def test_union_routes_int_arm(value):
    assert struct_of(UInt).resolve({"v": value}) == {"v": value}


@pytest.mark.parametrize("value", ["", "hi", "a longer string"])
def test_union_routes_str_arm(value):
    assert struct_of(UInt).resolve({"v": value}) == {"v": value}


@pytest.mark.parametrize("value", [1.5, True, [], (), b"x"])
def test_union_rejects_foreign_types(value):
    with pytest.raises(TypeError, match="expected int"):
        struct_of(UInt).resolve({"v": value})


@pytest.mark.parametrize("value", [5, "x", None])
def test_triple_union_routes_each_arm(value):
    assert struct_of(UTriple).resolve({"v": value}) == {"v": value}


@pytest.mark.parametrize("value", [date(2021, 5, 5), time(8, 30)])
def test_date_time_union_routes(value):
    assert struct_of(UDateTime).resolve({"v": value}) == {"v": value}


def _list_shape(min_len=None, max_len=None):
    kwargs = {}
    if min_len is not None:
        kwargs["min"] = _Min(min_len)
    if max_len is not None:
        kwargs["max"] = _Max(max_len)
    return List(item=(Int(),), **kwargs)


@pytest.mark.parametrize("length", range(0, 8))
def test_list_min_length_sweep(length):
    shape = _list_shape(min_len=3)
    payload = list(range(length))
    if length >= 3:
        shape._check(payload)
    else:
        with pytest.raises(ValueError, match="too few"):
            shape._check(payload)


@pytest.mark.parametrize("length", range(0, 8))
def test_list_max_length_sweep(length):
    shape = _list_shape(max_len=4)
    payload = list(range(length))
    if length <= 4:
        shape._check(payload)
    else:
        with pytest.raises(ValueError, match="too many"):
            shape._check(payload)


@pytest.mark.parametrize("length", range(0, 8))
def test_list_bounded_range_sweep(length):
    shape = _list_shape(min_len=2, max_len=5)
    payload = list(range(length))
    if 2 <= length <= 5:
        shape._check(payload)
    else:
        with pytest.raises(ValueError):
            shape._check(payload)


@pytest.mark.parametrize("bad_index", range(0, 5))
def test_list_reports_failing_item_index(bad_index):
    @dataclass
    class M:
        xs: list[Annotated[int, Min(0)]] = field(default_factory=list)

    payload = [0] * 5
    payload[bad_index] = -1
    with pytest.raises(ValueError, match=rf"\[{bad_index}\]"):
        struct_of(M).resolve({"xs": payload})


@dataclass
class Chain:
    value: int = 0
    next: "Chain | None" = None


@pytest.mark.parametrize("depth", range(1, 10))
def test_recursive_chain_resolves_at_depth(depth):
    data = None
    for i in range(depth):
        data = {"value": i, "next": data}
    result = struct_of(Chain).resolve(data)
    node = result
    for i in range(depth - 1, -1, -1):
        assert node["value"] == i
        node = node["next"]


@pytest.mark.parametrize("depth", range(1, 6))
def test_recursive_chain_rejects_bad_leaf(depth):
    data = "not a dict"
    for i in range(depth):
        data = {"value": i, "next": data}
    with pytest.raises(TypeError):
        struct_of(Chain).resolve(data)


@pytest.mark.parametrize("value", [
    1.5, True, False, [], (), {}, b"bytes", 3j, object(), "3.0",
])
def test_union_int_none_rejects_many_foreigns(value):
    @dataclass
    class M:
        v: int | None = None

    with pytest.raises(TypeError):
        struct_of(M).resolve({"v": value})


@pytest.mark.parametrize("length", range(0, 12))
def test_list_exact_length_via_equal_bounds(length):
    shape = List(item=(Int(),), min=_Min(3), max=_Max(3))
    payload = list(range(length))
    if length == 3:
        shape._check(payload)
    else:
        with pytest.raises(ValueError):
            shape._check(payload)


@pytest.mark.parametrize("payload", [
    [1, 2, 3],
    [0],
    list(range(100)),
])
def test_list_of_ints_valid(payload):
    List(item=(Int(),))._check(payload)


@pytest.mark.parametrize("bad_at", range(0, 4))
def test_list_reports_first_bad_item(bad_at):
    payload = ["a", "b", "c", "d"]
    payload[bad_at] = 5
    with pytest.raises(TypeError, match=rf"\[{bad_at}\]"):
        List(item=(Str(),))._check(payload)


@dataclass
class Person:
    name: str = "x"
    age: int = 0


@pytest.mark.parametrize("n", range(0, 6))
def test_list_of_dataclasses_resolves(n):
    @dataclass
    class Team:
        members: list[Person] = field(default_factory=list)

    data = {"members": [{"name": f"p{i}", "age": i} for i in range(n)]}
    result = struct_of(Team).resolve(data)
    assert len(result["members"]) == n


@pytest.mark.parametrize("depth", range(1, 21))
def test_deep_recursive_chain(depth):
    data = None
    for i in range(depth):
        data = {"value": i, "next": data}
    result = struct_of(Chain).resolve(data)
    count = 0
    node = result
    while node is not None:
        count += 1
        node = node["next"]
    assert count == depth


@dataclass
class MutualA:
    b: "MutualB | None" = None


@dataclass
class MutualB:
    a: "MutualA | None" = None


def test_mutual_recursion_compiles_and_resolves():
    schema = struct_of(MutualA)
    assert schema.resolve({"b": {"a": {"b": None}}}) == {"b": {"a": {"b": None}}}


@pytest.mark.parametrize("rows", [
    [[1, 2], [3, 4]],
    [[0]],
    [[i for i in range(5)] for _ in range(5)],
])
def test_nested_list_of_lists_valid(rows):
    @dataclass
    class M:
        grid: list[list[int]] = field(default_factory=list)

    assert struct_of(M).resolve({"grid": rows}) == {"grid": rows}


@pytest.mark.parametrize("i,j", [(0, 0), (1, 1), (2, 0)])
def test_nested_list_of_lists_reports_path(i, j):
    @dataclass
    class M:
        grid: list[list[Annotated[int, Min(0)]]] = field(default_factory=list)

    rows = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    rows[i][j] = -1
    with pytest.raises(ValueError, match=rf"\[{i}\]: \[{j}\]: too small"):
        struct_of(M).resolve({"grid": rows})

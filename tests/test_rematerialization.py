from dataclasses import dataclass, field
from datetime import date, time
from enum import Enum

import pytest

from pytypehint import signature_of, struct_of


class Role(Enum):
    ADMIN = "admin"
    USER = "user"


@dataclass
class Point:
    x: int = 0
    y: int = 0


# --- the per-kind table: what a fresh serving is, kind by kind ---


def test_scalar_defaults_pass_as_is():
    @dataclass
    class C:
        i: int = 5
        f: float = 1.5
        s: str = "hi"
        b: bool = True
        d: date = date(2020, 1, 1)
        t: time = time(9, 0)

    assert struct_of(C).resolve({}) == {
        "i": 5, "f": 1.5, "s": "hi", "b": True,
        "d": date(2020, 1, 1), "t": time(9, 0),
    }


def test_none_default_passes_as_is():
    @dataclass
    class C:
        x: int | None = None

    assert struct_of(C).resolve({})["x"] is None


def test_enum_member_default_is_shared_by_reference():   # I4
    @dataclass
    class C:
        role: Role = Role.ADMIN

    s = struct_of(C)
    a = s.resolve({})["role"]
    b = s.resolve({})["role"]
    assert a is Role.ADMIN
    assert a is b


def test_list_default_is_fresh_each_serving():
    @dataclass
    class C:
        xs: list[int] = field(default_factory=lambda: [1, 2])

    s = struct_of(C)
    a = s.resolve({})["xs"]
    b = s.resolve({})["xs"]
    assert a == b == [1, 2]
    assert a is not b


def test_nested_list_default_is_deep_fresh():
    def fn(m: list[list[int]] = [[1], [2]]):
        ...

    sig = signature_of(fn)
    a = sig.resolve({})["m"]
    b = sig.resolve({})["m"]
    assert a == b == [[1], [2]]
    assert a is not b
    assert a[0] is not b[0]


def test_instance_default_is_reconstructed_fresh():
    @dataclass
    class C:
        p: Point = field(default_factory=lambda: Point(1, 2))

    s = struct_of(C)
    a = s.resolve({})["p"]
    b = s.resolve({})["p"]
    assert a == b == Point(1, 2)
    assert a is not b


def test_nested_instance_default_is_reconstructed_deeply():
    @dataclass
    class Inner:
        xs: list[int] = field(default_factory=lambda: [1])

    @dataclass
    class Outer:
        inner: Inner = field(default_factory=Inner)

    s = struct_of(Outer)
    a = s.resolve({})["inner"]
    b = s.resolve({})["inner"]
    assert a is not b
    assert a.xs is not b.xs          # the inner list is fresh too, not just the shell


def test_factory_default_reruns_each_serving():
    @dataclass
    class C:
        xs: list[int] = field(default_factory=list)

    s = struct_of(C)
    assert s.resolve({})["xs"] is not s.resolve({})["xs"]


def test_function_mutable_literal_default_is_fresh():
    # the syntax every linter warns about, made correct by the schema
    def fn(tags: list[str] = []):
        ...

    sig = signature_of(fn)
    a = sig.resolve({})["tags"]
    b = sig.resolve({})["tags"]
    assert a == b == []
    assert a is not b


# --- I1: no build/resolve ever shares mutable default state, at any depth ---


def test_no_shared_default_state_at_any_depth():
    @dataclass
    class Deep:
        rows: list[list[Point]] = field(default_factory=lambda: [[Point(1, 1)]])

    s = struct_of(Deep)
    a = s.resolve({})["rows"]
    b = s.resolve({})["rows"]
    assert a is not b
    assert a[0] is not b[0]
    assert a[0][0] is not b[0][0]
    assert a[0][0] == b[0][0] == Point(1, 1)


# --- I2: input values pass by reference, untransformed ---


def test_present_value_passes_by_reference():
    @dataclass
    class C:
        xs: list[int] = field(default_factory=list)

    mine = [9, 9]
    assert struct_of(C).resolve({"xs": mine})["xs"] is mine


# --- I3: recipe execution count — the guard against caching the first serving ---


def test_recipe_runs_once_at_compile_once_per_missing_never_when_present():
    calls = []

    def make():
        calls.append(1)
        return [len(calls)]

    @dataclass
    class C:
        xs: list[int] = field(default_factory=make)

    assert calls == []                  # not run at class definition
    s = struct_of(C)
    assert len(calls) == 1              # exactly once at compile (certification)
    s.resolve({})
    assert len(calls) == 2              # once per missing-key resolve
    s.resolve({})
    assert len(calls) == 3
    s.resolve({"xs": [0]})              # present key → recipe not run
    assert len(calls) == 3


def test_constructor_recipe_runs_per_missing_serving():
    counter = {"n": 0}

    @dataclass
    class Opt:
        def __post_init__(self):
            counter["n"] += 1

    @dataclass
    class C:
        opt: Opt = field(default_factory=Opt)

    s = struct_of(C)
    assert counter["n"] == 1           # compile
    s.resolve({})
    s.resolve({})
    assert counter["n"] == 3           # + one per missing-key resolve
    with pytest.raises(TypeError, match="opt: expected dict, got Opt instance"):
        s.resolve({"opt": Opt()})
    assert counter["n"] == 4


# --- recursion: a recursive type carrying a default ---


@dataclass
class Node:
    v: int = 0
    kids: "list[Node]" = field(default_factory=list)


@dataclass
class NodeWithChild:
    value: int = 0
    children: list["NodeWithChild"] = field(
        default_factory=lambda: [NodeWithChild(value=1, children=[])])


def test_recursive_type_with_default_rematerializes_fresh():
    s = struct_of(Node)
    a = s.resolve({})["kids"]
    b = s.resolve({})["kids"]
    assert a == b == []
    assert a is not b


def test_recursive_instance_factory_certifies_after_graph_and_builds_fresh():
    schema = struct_of(NodeWithChild)
    a = schema.build({})
    b = schema.build({})

    assert [child.value for child in a.children] == [1]
    assert [child.value for child in b.children] == [1]
    assert a.children[0].children == b.children[0].children == []
    assert a.children is not b.children
    assert a.children[0] is not b.children[0]

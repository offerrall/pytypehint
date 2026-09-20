"""Tuple contracts across compilation, exact input and portable data."""

import json
from dataclasses import FrozenInstanceError, dataclass, field, make_dataclass
from datetime import date
from enum import Enum
from typing import Annotated, Literal, Tuple as TypingTuple

import pytest
from hypothesis import given, strategies as st

from pytypehint import (
    Extra, Field, Float, Int, Label, Max, Min, NoneShape, SchemaTypeError,
    SchemaValueError, Str, Tuple, signature_of, struct_of,
)


def schema_of(hint):
    return struct_of(make_dataclass("Model", [("value", hint)]))


@pytest.mark.parametrize("hint, value, identity", [
    (tuple[int, str], (3, "a"), "tuple[int, str]"),
    (tuple[int], (3,), "tuple[int]"),
    (tuple[()], (), "tuple[()]"),
    (TypingTuple[()], (), "tuple[()]"),
    (TypingTuple[int, str], (3, "a"), "tuple[int, str]"),
    (TypingTuple[int, ...], (), "tuple[int, ...]"),
    (tuple[int, ...], (1, 2, 3), "tuple[int, ...]"),
    (tuple[int | str | None, ...], (1, "a", None), "tuple[int | str | None, ...]"),
    (tuple[list[int], tuple[str, ...]], ([1], ("a", "b")), "tuple[list[int], tuple[str, ...]]"),
])
def test_standard_forms(hint, value, identity):
    schema = schema_of(hint)
    shape = schema.fields[0].shape[0]
    assert type(shape) is Tuple
    assert shape.option_id() == identity
    assert schema.resolve({"value": value})["value"] is value
    assert schema.build({"value": value}).value == value


@pytest.mark.parametrize("hint, value, error, path", [
    (tuple[int], [1], SchemaTypeError, ("value",)),
    (tuple[int], (), SchemaValueError, ("value",)),
    (tuple[int], (1, 2), SchemaValueError, ("value",)),
    (tuple[()], (1,), SchemaValueError, ("value",)),
    (tuple[int, str], (True, "a"), SchemaTypeError, ("value", 0)),
    (tuple[float, ...], (0.0, 1), SchemaTypeError, ("value", 1)),
    (tuple[float, ...], (float("nan"),), SchemaValueError, ("value", 0)),
    (list[tuple[int]], [(1,), (False,)], SchemaTypeError, ("value", 1, 0)),
    (tuple[Annotated[int, Min(0)], str], (-1, "a"), SchemaValueError, ("value", 0)),
])
def test_exact_values_and_error_coordinates(hint, value, error, path):
    schema = schema_of(hint)
    for operation in (schema.resolve, schema.build):
        with pytest.raises(error) as failure:
            operation({"value": value})
        assert failure.value.path == path


def test_subclasses_are_never_coerced():
    class ForeignTuple(tuple):
        pass

    class ForeignList(list):
        pass

    schema = schema_of(tuple[int, ...])
    for value in (ForeignTuple((1,)), ForeignList([1])):
        assert schema.decode({"value": value})["value"] is value
        with pytest.raises(SchemaTypeError):
            schema.build({"value": value})


@pytest.mark.parametrize("hint", [tuple, TypingTuple, tuple[...], tuple[int, ..., str],
                                  tuple[..., ...], tuple[None], tuple[None, ...]])
def test_incomplete_or_invalid_hints_are_rejected(hint):
    with pytest.raises(TypeError):
        schema_of(hint)


@pytest.mark.parametrize("hint, message", [
    (tuple[Annotated[int, Label("Item")]], "field atoms cannot apply to tuple items"),
    (tuple[Literal["a"] | str], "both compile to str"),
    (tuple[Annotated[int | str, Min(0)]], "must go per option"),
    (tuple[Annotated[int, Min(0)]] | tuple[Annotated[int, Max(9)]], "duplicate option types"),
])
def test_metadata_and_identity_rules(hint, message):
    with pytest.raises((TypeError, ValueError), match=message):
        schema_of(hint)


@pytest.mark.parametrize("kwargs, error", [
    ({"items": []}, TypeError),
    ({"items": ((),)}, TypeError),
    ({"items": ((int,),)}, TypeError),
    ({"items": ((Int(), Int()),)}, ValueError),
    ({"items": ((NoneShape(),),)}, TypeError),
    ({"items": (), "variadic": 1}, TypeError),
    ({"items": (), "variadic": True}, ValueError),
    ({"items": ((Int(),), (Str(),)), "variadic": True}, ValueError),
    ({"items": (), "min": Min(1)}, ValueError),
    ({"items": ((Int(),),), "max": Max(0)}, ValueError),
    ({"items": (), "min": Min(-1)}, ValueError),
    ({"items": (), "max": Max(1.0)}, TypeError),
    ({"items": (), "min": Min(0, exclusive=True)}, ValueError),
    ({"items": (), "_extras": (("a.x", "1"), ("a.x", "2"))}, ValueError),
])
def test_manual_shape_invariants(kwargs, error):
    with pytest.raises(error):
        Tuple(**kwargs)


def test_shapes_are_frozen_hashable_and_extras_are_detached():
    shape = Tuple(items=((Int(), Str()),), variadic=True, _extras=(("ui.x", "a"),))
    assert shape == Tuple(items=((Int(), Str()),), variadic=True, _extras=(("ui.x", "a"),))
    assert hash(shape) == hash(shape)
    with pytest.raises(FrozenInstanceError):
        shape.variadic = False
    extras = shape.extras
    extras.clear()
    assert shape.extras == {"ui.x": "a"}


def test_length_atoms_and_position_atoms_are_independent():
    hint = Annotated[tuple[Annotated[int, Min(0)], ...], Min(1), Max(2), Extra("ui.kind", "pair")]
    schema = schema_of(hint)
    assert schema.build({"value": (0, 2)}).value == (0, 2)
    for value, leaf in [((), "too few items"), ((1, 2, 3), "too many items"), ((-1,), "too small")]:
        with pytest.raises(SchemaValueError, match=leaf):
            schema.build({"value": value})
    schema_of(Annotated[tuple[int, str], Min(2), Max(2)])


@dataclass
class Child:
    n: int = 7


@dataclass
class Node:
    children: tuple["Node", ...] = ()


def test_nested_dataclasses_resolve_build_and_recursive_contract():
    schema = schema_of(tuple[Child, list[Child]])
    value = ({}, [{"n": 3}])
    assert schema.resolve({"value": value})["value"] is value
    result = schema.build({"value": value}).value
    assert result == (Child(), [Child(3)])
    assert result[1] is not value[1]
    with pytest.raises(SchemaTypeError, match="got Child instance"):
        schema.build({"value": (Child(), [])})
    tree = struct_of(Node)
    assert tree.build(tree.decode({"children": [{"children": [{}]}]})) == Node((Node((Node(),)),))
    assert list(tree.to_dict()["defs"]["structs"]) == ["Node"]
    with pytest.raises(SchemaTypeError) as failure:
        tree.build({"children": ({"children": (3,)},)})
    assert failure.value.path == ("children", 0, "children", 0)


def test_defaults_rebuild_mutable_contents_and_instances():
    def process(value: tuple[list[int], Child] = ([1], Child())):
        return value

    schema = signature_of(process)
    first = schema.build({})["value"]
    second = schema.build({})["value"]
    first[0].append(9)
    first[1].n = 99
    assert second == ([1], Child())
    assert schema.params[0].default == ([1], Child())


@pytest.mark.parametrize("value", [(), (1, 2), [1], (False,)])
def test_invalid_defaults_are_not_truncated_or_coerced(value):
    with pytest.raises((SchemaTypeError, SchemaValueError)) as failure:
        Field(name="value", shape=(Tuple(items=((Int(),),)),), default=value)
    assert failure.value.path[:2] == ("value", "default")


def test_factory_is_revalidated_at_each_serving():
    current = (1,)

    @dataclass
    class Model:
        value: tuple[int] = field(default_factory=lambda: current)

    schema = struct_of(Model)
    current = (1, 2)
    with pytest.raises(SchemaValueError) as failure:
        schema.build({})
    assert failure.value.path == ("value", "default")


def test_union_requires_explicit_identity_even_if_length_identifies_it():
    schema = schema_of(tuple[int] | tuple[str, str])
    with pytest.raises(SchemaTypeError, match="ambiguous tuple"):
        schema.build({"value": (1,)})
    data = {"value": {"$type": "tuple[int]", "$value": (1,)}}
    assert schema.resolve(data) == data
    assert schema.build(data).value == (1,)
    wire = {"value": {"$type": "tuple[str, str]", "$value": ["a", "b"]}}
    assert schema.build(schema.decode(wire)).value == ("a", "b")
    with pytest.raises(SchemaTypeError) as failure:
        schema.build({"value": {"$type": "tuple[int]", "$value": (True,)}})
    assert failure.value.path == ("value", "$value", 0)


def test_list_tuple_portable_collision_never_guesses_from_contents():
    schema = schema_of(list[int] | tuple[str, ...])
    assert schema.decode({"value": ["a"]}) == {"value": ["a"]}
    with pytest.raises(SchemaTypeError):
        schema.build(schema.decode({"value": ["a"]}))
    wire = {"value": {"$type": "tuple[str, ...]", "$value": ["a"]}}
    assert schema.decode(wire) == {"value": ("a",)}
    assert schema.build(schema.decode(wire)).value == ("a",)
    assert schema.build({"value": [1]}).value == [1]


class Role(Enum):
    USER = "user"


@pytest.mark.parametrize("hint, default", [
    (tuple[()], ()),
    (tuple[date, Role, float], (date(2026, 9, 20), Role.USER, 1.0)),
    (tuple[str | date, int | float], (date(2026, 9, 20), 2.0)),
    (tuple[Child, ...], (Child(), Child(3))),
    (tuple[list[int], tuple[str, ...]], ([1], ("a",))),
    (tuple[int, ...] | tuple[str, ...], ()),
    (list[int] | tuple[int, ...], (1, 2)),
    (tuple[tuple[int, ...] | tuple[str, ...], ...], ((1,), ("a",))),
])
def test_portable_default_round_trip(hint, default):
    cls = make_dataclass("Model", [("value", hint, field(default_factory=lambda: default))])
    schema = struct_of(cls)
    doc = json.loads(json.dumps(schema.to_dict(), allow_nan=False))
    written = doc["defs"]["structs"]["Model"]["fields"][0]["default"]
    assert schema.build(schema.decode({"value": written})).value == default
    assert schema.to_dict() == struct_of(cls).to_dict()


@pytest.mark.parametrize("hint, expected", [
    (tuple[int, str], {"type": "tuple", "items": [[{"type": "int"}], [{"type": "str"}]]}),
    (tuple[()], {"type": "tuple", "items": []}),
    (tuple[int, ...], {"type": "tuple", "item": [{"type": "int"}]}),
])
def test_portable_schema_states_positional_or_repeated_items(hint, expected):
    doc = schema_of(hint).to_dict()
    assert doc["v"] == 1
    assert doc["defs"]["structs"]["Model"]["fields"][0]["shape"] == [expected]


def test_decode_preserves_invalid_lengths_and_extra_data():
    schema = schema_of(tuple[date])
    data = {"value": ["2026-09-20", {"unknown": [1]}]}
    decoded = schema.decode(data)
    assert decoded == {"value": (date(2026, 9, 20), {"unknown": [1]})}
    decoded["value"][1]["unknown"].append(2)
    assert data["value"][1]["unknown"] == [1]
    for wire in (data, {"value": []}):
        with pytest.raises(SchemaValueError, match="expected 1 items"):
            schema.build(schema.decode(wire))


@given(st.lists(st.integers(), max_size=30))
def test_variadic_portable_round_trip(values):
    schema = schema_of(tuple[int, ...])
    decoded = schema.decode({"value": values})
    assert decoded == {"value": tuple(values)}
    assert schema.decode(decoded) == decoded
    assert schema.build(decoded).value == tuple(values)


def test_tuple_item_discriminators_cover_dataclasses_and_containers():
    @dataclass
    class Other:
        text: str

    schema = schema_of(tuple[Child | Other, tuple[int, ...] | tuple[str, ...]])
    wire = {"value": [{"$type": "Other", "text": "ok"},
                      {"$type": "tuple[int, ...]", "$value": [1, 2]}]}
    assert schema.build(schema.decode(wire)).value == (Other("ok"), (1, 2))
    with pytest.raises(SchemaTypeError) as failure:
        schema.build({"value": ({"$type": "Other", "text": 3},
                                {"$type": "tuple[int, ...]", "$value": (1,)})})
    assert failure.value.path == ("value", 0, "text")


def test_tuple_slots_reject_discriminator_name_collisions():
    namesake = Enum("int", {"A": 1})
    with pytest.raises(ValueError, match="duplicate discriminator name"):
        schema_of(tuple[int | namesake])


@dataclass
class Link:
    next: tuple["Link | None"] = (None,)


def test_fixed_recursive_defaults_are_certified_after_the_graph_exists():
    schema = struct_of(Link)
    assert schema.build({}) == Link()
    assert schema.build({"next": ({},)}) == Link((Link(),))
    assert schema.to_dict()["defs"]["structs"]["Link"]["fields"][0]["default"] == [None]


def test_malformed_portable_tuple_wrapper_cannot_fall_into_a_list_option():
    schema = schema_of(tuple[int, ...] | list[int])
    for wrapper in ({"$type": "tuple[int, ...]", "$value": "bad"},
                    {"$type": "tuple[int, ...]", "$value": [1], "extra": True}):
        assert schema.decode({"value": wrapper}) == {"value": wrapper}
        with pytest.raises(SchemaTypeError):
            schema.build(schema.decode({"value": wrapper}))


def test_build_checks_tuple_input_items_only_once(monkeypatch):
    count = 0
    original = Float._check

    def counted(self, value):
        nonlocal count
        count += 1
        return original(self, value)

    schema = schema_of(tuple[float, ...])
    monkeypatch.setattr(Float, "_check", counted)
    assert schema.build({"value": (1.0, 2.0, 3.0)}).value == (1.0, 2.0, 3.0)
    assert count == 3

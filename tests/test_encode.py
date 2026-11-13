"""`encode`: a valid instance written as the portable tree `decode` reads.

docs/encode.md promises one thing above the rest: for a valid value,
`schema.build(schema.decode(schema.encode(value)))` gives the value back, also
after a real JSON transport. The examples pin the spellings; the corpus borrowed
from `test_portable_properties` pins the promise across every schema its
generator can compose, against that module's independent test encoder.
"""

import json
import random
from copy import deepcopy
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, time, timedelta, timezone
from enum import Enum
from typing import Annotated, Literal

import pytest

import pytypehint
from pytypehint import (
    Max, Min, SchemaTypeError, SchemaValueError, Signature, Struct, immutable,
    signature_of, struct_of,
)

from test_portable_properties import (
    _ALL, _DEFAULTED, _encode as _reference_encode, _sample_options,
)

_PORTABLE_TYPES = (dict, list, str, int, float, bool, type(None))


def _same(left, right) -> bool:
    """Equality that also compares types, so 1, 1.0 and True stay apart."""
    if type(left) is not type(right):
        return False
    if is_dataclass(left):
        return all(_same(getattr(left, f.name), getattr(right, f.name))
                   for f in fields(left))
    if type(left) in (list, tuple):
        return len(left) == len(right) and all(map(_same, left, right))
    if type(left) is dict:
        return left.keys() == right.keys() and all(
            _same(left[key], right[key]) for key in left)
    if type(left) is float:
        return repr(left) == repr(right)
    return left == right


def _only_portable(tree) -> bool:
    if type(tree) is dict:
        return all(type(k) is str and _only_portable(v) for k, v in tree.items())
    if type(tree) is list:
        return all(_only_portable(v) for v in tree)
    return type(tree) in _PORTABLE_TYPES


def _round_trip(schema, value):
    wire = json.loads(json.dumps(schema.encode(value)))
    return schema.build(schema.decode(wire))


class _Role(Enum):
    ADMIN = "admin"
    USER = "user"


class _Status(Enum):
    OPEN = 1
    CLOSED = 2


@dataclass
class _Cat:
    name: str


@dataclass
class _Dog:
    name: str
    born: date | None = None


@dataclass
class _Spellings:
    count: int
    ratio: float
    day: date
    at: time
    role: _Role
    pet: _Cat
    tags: list[str]
    pair: tuple[int, str]
    nothing: int | None = None


# ------------------------------------------------------------- the spellings

def test_each_type_is_written_in_its_portable_spelling():
    value = _Spellings(count=3, ratio=1.5, day=date(2026, 8, 8), at=time(14, 30),
                       role=_Role.ADMIN, pet=_Cat("Tom"), tags=["a", "b"],
                       pair=(1, "x"))

    assert struct_of(_Spellings).encode(value) == {
        "count": 3, "ratio": 1.5, "day": "2026-08-08", "at": "14:30:00",
        "role": "ADMIN", "pet": {"name": "Tom"}, "tags": ["a", "b"],
        "pair": [1, "x"], "nothing": None,
    }


@dataclass
class _Unions:
    number: int | float
    text: str | date
    moment: date | time
    state: _Role | _Status
    pet: _Cat | _Dog
    items: list[int] | list[str]
    sequence: list[int] | tuple[int, ...]
    plain: int | str | None
    mixed: list[str | date]


@pytest.mark.parametrize("name, value, written", [
    ("number", 3, {"$type": "int", "$value": 3}),
    ("number", 3.0, {"$type": "float", "$value": 3.0}),
    ("text", "2026-08-08", {"$type": "str", "$value": "2026-08-08"}),
    ("text", date(2026, 8, 8), {"$type": "date", "$value": "2026-08-08"}),
    ("moment", time(9, 30), {"$type": "time", "$value": "09:30:00"}),
    ("state", _Status.OPEN, {"$type": "_Status", "$value": "OPEN"}),
    ("pet", _Dog("Rex", date(2020, 1, 2)),
     {"$type": "_Dog", "name": "Rex", "born": "2020-01-02"}),
    ("items", ["a"], {"$type": "list[str]", "$value": ["a"]}),
    ("sequence", [1], {"$type": "list[int]", "$value": [1]}),
    ("sequence", (1, 2), {"$type": "tuple[int, ...]", "$value": [1, 2]}),
    ("plain", 3, 3),
    ("plain", "three", "three"),
    ("plain", None, None),
    ("mixed", ["a", date(2026, 8, 8)],
     [{"$type": "str", "$value": "a"}, {"$type": "date", "$value": "2026-08-08"}]),
])
def test_an_option_is_named_exactly_where_its_spelling_collides(name, value, written):
    base = dict(number=1, text="t", moment=date(2026, 1, 1), state=_Role.USER,
                pet=_Cat("Tom"), items=[1], sequence=[1], plain=None, mixed=[])
    instance = _Unions(**{**base, name: value})
    schema = struct_of(_Unions)

    assert schema.encode(instance)[name] == written
    assert _same(_round_trip(schema, instance), instance)


@dataclass
class _Tuples:
    empty: tuple[()]
    single: tuple[int]
    fixed: tuple[int | float, date | None, _Cat]
    variadic: tuple[_Cat | _Dog, ...]
    nested: tuple[tuple[int, ...], list[tuple[str, time]]]
    either: tuple[int] | tuple[str] | tuple[int, str]
    bounded: Annotated[tuple[float, ...], Min(1), Max(3)] = (0.5,)


@pytest.mark.parametrize("either", [(3,), ("three",), (3, "three")])
def test_tuples_are_written_as_arrays_and_read_back_as_tuples(either):
    value = _Tuples(
        empty=(), single=(7,), fixed=(2.0, None, _Cat("Tom")),
        variadic=(_Cat("Tom"), _Dog("Rex")),
        nested=((1, 2), [("a", time(1, 2, 3))]), either=either)
    schema = struct_of(_Tuples)
    written = schema.encode(value)

    assert written["empty"] == [] and written["single"] == [7]
    assert written["fixed"] == [{"$type": "float", "$value": 2.0}, None, {"name": "Tom"}]
    assert written["variadic"] == [{"$type": "_Cat", "name": "Tom"},
                                   {"$type": "_Dog", "name": "Rex", "born": None}]
    assert written["nested"] == [[1, 2], [["a", "01:02:03"]]]
    assert set(written["either"]) == {"$type", "$value"}
    assert _only_portable(written)
    assert _same(_round_trip(schema, value), value)


@dataclass
class _Tree:
    label: str
    children: list["_Tree"] = field(default_factory=list)


def test_a_recursive_value_is_written_to_its_full_depth():
    tree = _Tree("root", [_Tree("a", [_Tree("b")]), _Tree("c")])
    schema = struct_of(_Tree)

    assert schema.encode(tree) == {
        "label": "root",
        "children": [
            {"label": "a", "children": [{"label": "b", "children": []}]},
            {"label": "c", "children": []},
        ],
    }
    assert _same(_round_trip(schema, tree), tree)


@immutable
class _Exposure:
    stops: float = 0.0


@immutable
class _Grayscale:
    pass


@immutable
class _Layer:
    name: Annotated[str, Min(1)]
    effect: _Exposure | _Grayscale
    color: tuple[float, float, float] = (0.0, 0.0, 1.0)


def test_immutable_models_encode_through_struct_of():
    layer = _Layer(name="Photo", effect=_Exposure(stops=1.5))
    schema = struct_of(_Layer)

    assert schema.encode(layer) == {
        "name": "Photo", "effect": {"$type": "_Exposure", "stops": 1.5},
        "color": [0.0, 0.0, 1.0]}
    assert _round_trip(schema, layer) == layer


def test_a_signed_zero_survives():
    @dataclass
    class Zero:
        value: float

    written = struct_of(Zero).encode(Zero(-0.0))
    assert repr(written["value"]) == "-0.0"
    assert _same(_round_trip(struct_of(Zero), Zero(-0.0)), Zero(-0.0))


# ----------------------------------------------------------------- signatures

def _search(query: str, day: date, limit: int | float = 10, page: _Cat | None = None):
    return query


def test_a_signature_encodes_the_arguments_it_is_given():
    schema = signature_of(_search)
    kwargs = {"query": "q", "day": date(2026, 8, 8), "limit": 2.0, "page": _Cat("Tom")}

    assert schema.encode(kwargs) == {
        "query": "q", "day": "2026-08-08",
        "limit": {"$type": "float", "$value": 2.0}, "page": {"name": "Tom"}}
    assert _same(schema.build(schema.decode(schema.encode(kwargs))), kwargs)


def test_a_signature_encodes_a_partial_set_of_arguments_without_filling_defaults():
    assert signature_of(_search).encode({"day": date(2026, 8, 8)}) == {"day": "2026-08-08"}
    assert signature_of(_search).encode({}) == {}


def test_what_build_returns_is_what_encode_takes():
    schema = signature_of(_search)
    kwargs = schema.build(schema.decode({"query": "q", "day": "2026-08-08"}))

    assert schema.encode(kwargs) == {
        "query": "q", "day": "2026-08-08",
        "limit": {"$type": "int", "$value": 10}, "page": None}


@pytest.mark.parametrize("kwargs, message", [
    ([], "expected dict, got list"),
    ({1: "q"}, "expected string keys, got int"),
    ({"query": "q", "extra": 1, "other": 2}, "unexpected argument(s): extra, other"),
])
def test_a_signature_refuses_what_it_cannot_name(kwargs, message):
    with pytest.raises(SchemaTypeError) as error:
        signature_of(_search).encode(kwargs)
    assert str(error.value) == message


# --------------------------------------------------------------------- errors

@pytest.mark.parametrize("value", [
    {"name": "Tom"}, _Dog("Rex"), None, "Tom",
    type("_Cat", (_Cat,), {})("Tom"),
])
def test_the_root_must_be_an_exact_instance_of_the_class(value):
    with pytest.raises(SchemaTypeError, match=r"^expected _Cat, got "):
        struct_of(_Cat).encode(value)


@dataclass
class _Order:
    pets: list[_Cat | _Dog]
    pair: tuple[int, str]
    amount: Annotated[list[str], Min(1)] | list[int] = field(default_factory=list)


def test_a_value_no_option_owns_is_reported_with_its_path():
    order = _Order(pets=[_Cat("Tom"), _Dog("Rex", born="2020-01-02")], pair=(1, "x"))

    with pytest.raises(SchemaTypeError) as error:
        struct_of(_Order).encode(order)
    assert error.value.path == ("pets", 1, "born")
    assert error.value.leaf == "expected date | NoneType, got str"


def test_a_tuple_of_the_wrong_length_is_reported_with_its_path():
    order = _Order(pets=[], pair=(1, "x", 2))

    with pytest.raises(SchemaValueError) as error:
        struct_of(_Order).encode(order)
    assert error.value.path == ("pair",)
    assert error.value.leaf == "expected 2 items, got 3"


def test_options_of_one_type_are_told_apart_by_their_limits_or_refused():
    schema = struct_of(_Order)

    assert schema.encode(_Order(pets=[], pair=(1, "x"), amount=["a"]))["amount"] == {
        "$type": "list[str]", "$value": ["a"]}
    assert schema.encode(_Order(pets=[], pair=(1, "x"), amount=[]))["amount"] == {
        "$type": "list[int]", "$value": []}

    with pytest.raises(SchemaValueError) as error:
        schema.encode(_Order(pets=[], pair=(1, "x"), amount=[1.5]))
    assert error.value.path == ("amount",)
    assert error.value.leaf == "matches no option: list[str] | list[int]"


# ------------------------------------------- encode writes; it does not judge

@dataclass
class _Limited:
    count: Annotated[int, Min(1)]
    at: time
    size: Literal["S", "M"] = "S"


@pytest.mark.parametrize("value, written, refusal", [
    (_Limited(0, time(1, 2, 3)), {"count": 0, "at": "01:02:03", "size": "S"},
     "count: too small: 0, minimum 1"),
    (_Limited(1, time(1, 2, 3, 500)), {"count": 1, "at": "01:02:03.000500", "size": "S"},
     "at: time precision is limited to whole seconds: 01:02:03.000500"),
    (_Limited(1, time(1, 2, 3, tzinfo=timezone(timedelta(hours=2)))),
     {"count": 1, "at": "01:02:03+02:00", "size": "S"},
     "at: must be naive (no tzinfo): 01:02:03+02:00"),
    (_Limited(1, time(1, 2, 3), size="XL"), {"count": 1, "at": "01:02:03", "size": "XL"},
     "size: not a choice: 'XL', expected one of ('S', 'M')"),
])
def test_a_value_outside_its_limits_is_written_faithfully_and_left_for_build(
        value, written, refusal):
    schema = struct_of(_Limited)

    assert schema.encode(value) == written
    with pytest.raises((SchemaTypeError, SchemaValueError)) as error:
        schema.build(schema.decode(schema.encode(value)))
    assert str(error.value) == refusal


def test_a_sequence_outside_its_length_limits_is_left_for_build_too():
    schema = struct_of(_Tuples)
    value = _Tuples(empty=(), single=(7,), fixed=(1, None, _Cat("Tom")), variadic=(),
                    nested=((), []), either=(3,), bounded=())

    assert schema.encode(value)["bounded"] == []
    with pytest.raises(SchemaValueError) as error:
        schema.build(schema.decode(schema.encode(value)))
    assert str(error.value) == "bounded: too few items: 0, minimum 1"


# ------------------------------------------------------------- preservation

def test_the_tree_shares_no_container_with_the_instance_and_leaves_it_untouched():
    value = _Spellings(count=3, ratio=1.5, day=date(2026, 8, 8), at=time(14, 30),
                       role=_Role.ADMIN, pet=_Cat("Tom"), tags=["a", "b"],
                       pair=(1, "x"))
    before = deepcopy(value)
    schema = struct_of(_Spellings)

    first, second = schema.encode(value), schema.encode(value)
    first["tags"].append("c")
    first["pet"]["name"] = "Changed"

    assert value == before
    assert second["tags"] == ["a", "b"] and second["pet"] == {"name": "Tom"}


def test_encode_is_a_method_on_both_compiled_schemas_and_not_an_export():
    assert "encode" not in pytypehint.__all__ and not hasattr(pytypehint, "encode")
    assert callable(Struct.encode) and callable(Signature.encode)


# ----------------------------------------------------------------- the corpus

def _samples(schema, rng, count=4):
    for _ in range(count):
        if type(schema) is Struct:
            yield _sample_options((schema,), rng, 3)
        else:
            yield {p.name: _sample_options(p.shape, rng, 3) for p in schema.params}


def _reference(schema, value):
    if type(schema) is Struct:
        return _reference_encode((schema,), value)
    return {p.name: _reference_encode(p.shape, value[p.name]) for p in schema.params}


def test_every_generated_value_is_written_as_the_reference_encoder_writes_it():
    rng = random.Random(1303)
    for schema in _ALL:
        for value in _samples(schema, rng):
            assert schema.encode(value) == _reference(schema, value)


def test_every_generated_value_survives_a_json_round_trip_with_its_types():
    rng = random.Random(2026)
    checked = 0
    for schema in _ALL:
        for value in _samples(schema, rng):
            written = schema.encode(value)
            assert _only_portable(written)
            assert _same(_round_trip(schema, value), value)
            checked += 1
    assert checked > 2000


def test_encode_is_deterministic_and_never_modifies_its_input():
    rng = random.Random(77)
    for schema in _ALL[::5]:
        for value in _samples(schema, rng, count=2):
            before = deepcopy(value)
            assert schema.encode(value) == schema.encode(value)
            assert _same(value, before)


def test_a_default_in_the_document_is_what_encode_writes_for_the_same_value():
    compared = 0
    for schema in _DEFAULTED.schemas:
        built = schema.build({})
        written = schema.encode(built)
        document = schema.to_dict()
        nodes = document["defs"]["structs"][document["root"]]["fields"]
        for node in nodes:
            assert node["default"] == written[node["name"]]
            compared += 1
    assert compared > 300

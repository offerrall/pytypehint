"""The boundary `decode` draws around itself.

Not the catalogue of what decode restores — that lives elsewhere — but the four
promises the operation makes about everything it does *not* do:

* docs/decode.md, '`decode` is not coercion': 'None of these happen, at any
  depth, under any schema'.
* docs/decode.md, 'What decode leaves alone': absent keys, unknown keys and a
  root that is not a dict travel through untouched.
* docs/decode.md, 'Fresh trees': 'decode never modifies the tree it is given,
  and never hands back a container from it'.
* docs/decode.md, 'Order': 'decode runs before resolve and build, never after'
  — and `build` never needs it.

docs/philosophy.md, 'Hints are exact': '`int` accepts values whose type is
exactly `int`, not `bool`, a subclass or a numeric string. Coercion is wrapper
policy and stays visible at that boundary.'
"""

import copy
from dataclasses import dataclass, field, make_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Annotated

import pytest

from pytypehint import (
    Choices, FileHint, Max, Min, MultipleOf, Pattern,
    SchemaTypeError, SchemaValueError, signature_of, struct_of,
)


# --------------------------------------------------------------- the fixtures
# Module-level and `_`-prefixed: there is no conftest and no fixture in this
# suite, so every schema below is built from these or from `make_dataclass`.


class _Role(Enum):
    ADMIN = "admin"
    USER = "user"


class _MyInt(int):
    pass


class _MyStr(str):
    pass


class _MyFloat(float):
    pass


@dataclass
class _Point:
    x: int = 0


@dataclass
class _Marker:
    """The partner option that makes `list[T] | list[_Marker]` need a wrapper."""
    tag: str = ""


@dataclass
class _Pair:
    left: _Point
    right: _Point


@dataclass
class _Lists:
    one: list[str]
    two: list[str]


@dataclass
class _Inner:
    when: date
    tags: list[str]


@dataclass
class _Node:
    """Module level so the forward reference resolves — the cycle is in the data, not the schema."""
    child: "_Node | None" = None


@dataclass
class _Everything:
    """One field per entry of docs/vocabulary.md, all of them required.

    Nothing here carries a default: decode has no interest in defaults, and a
    required field makes that plain — every test below that touches defaults
    builds its own dataclass.
    """
    n: int
    ratio: float
    name: str
    active: bool
    day: date
    at: time
    role: _Role
    items: list[int]
    matrix: list[list[date]]
    inner: _Inner
    choice: str | date
    either: list[str] | list[int]
    maybe: int | None


_SCHEMA = struct_of(_Everything)


# A portable tree that exercises every restoration decode performs.
_WIRE = {
    "n": 1,
    "ratio": 3,
    "name": "2026-08-08",
    "active": True,
    "day": "2026-08-08",
    "at": "14:30",
    "role": "ADMIN",
    "items": [1, 2],
    "matrix": [["2026-08-08"], []],
    "inner": {"when": "2000-01-01", "tags": ["1", "true"]},
    "choice": {"$type": "date", "$value": "2026-08-08"},
    "either": {"$type": "list[str]", "$value": ["a"]},
    "maybe": None,
}

# The same contract already in exact Python — a default, a fixture, a value
# built in Python. docs/decode.md, 'Order': '`decode` is unnecessary and `build`
# takes it directly'.
_EXACT = {
    "n": 1,
    "ratio": 3.0,
    "name": "2026-08-08",
    "active": True,
    "day": date(2026, 8, 8),
    "at": time(14, 30),
    "role": _Role.ADMIN,
    "items": [1, 2],
    "matrix": [[date(2026, 8, 8)], []],
    "inner": {"when": date(2000, 1, 1), "tags": ["1", "true"]},
    "choice": date(2026, 8, 8),
    "either": {"$type": "list[str]", "$value": ["a"]},
    "maybe": None,
}


# --------------------------------------------------------------- the helpers


def _container_ids(tree, found=None) -> set:
    """Every `id()` of a dict or a list reachable in `tree`.

    Only dicts and lists: docs/decode.md promises that 'every dict and list in
    the result is newly built', and says nothing about immutable containers,
    which decode hands back by reference because nobody can write to them.
    """
    if found is None:
        found = set()
    if type(tree) is dict:
        found.add(id(tree))
        for value in tree.values():
            _container_ids(value, found)
    elif type(tree) is list:
        found.add(id(tree))
        for value in tree:
            _container_ids(value, found)
    return found


def _types_of(tree):
    """The tree with every leaf replaced by its exact type.

    `==` alone cannot see a coercion: `1 == 1.0` and `True == 1`. Comparing the
    type skeletons makes the difference visible.
    """
    if type(tree) is dict:
        return {key: _types_of(value) for key, value in tree.items()}
    if type(tree) is list:
        return [_types_of(value) for value in tree]
    return type(tree)


def _placed(depth: str, field_type, option_id: str, value):
    """A schema, a payload carrying `value` at `depth`, and a reader for it.

    The five depths of docs/decode.md: the root of a dataclass, a list item, an
    item of a nested list, a field of a nested dataclass, and the payload of a
    discriminated `$value` wrapper.
    """
    if depth == "root":
        cls = make_dataclass("_Root", [("x", field_type)])
        return struct_of(cls), {"x": value}, lambda out: out["x"]

    if depth == "in_list":
        cls = make_dataclass("_Root", [("x", list[field_type])])
        return struct_of(cls), {"x": [value]}, lambda out: out["x"][0]

    if depth == "in_nested_list":
        cls = make_dataclass("_Root", [("x", list[list[field_type]])])
        return struct_of(cls), {"x": [[value]]}, lambda out: out["x"][0][0]

    if depth == "in_nested_struct":
        inner = make_dataclass("_Inner", [("x", field_type)])
        cls = make_dataclass("_Root", [("inner", inner)])
        return struct_of(cls), {"inner": {"x": value}}, lambda out: out["inner"]["x"]

    if depth == "in_wrapper_value":
        # Two list options share a Python type, so the wrapper is accepted and
        # kept — docs/decode.md, 'Unions' — and only its payload is decoded.
        cls = make_dataclass("_Root", [("x", list[field_type] | list[_Marker])])
        data = {"x": {"$type": f"list[{option_id}]", "$value": [value]}}
        return struct_of(cls), data, lambda out: out["x"]["$value"][0]

    raise AssertionError(f"unknown depth {depth!r}")


_DEPTHS = ("root", "in_list", "in_nested_list", "in_nested_struct", "in_wrapper_value")


# =========================================================================
# 1. decode is not coercion
# =========================================================================

# (id, field type, the option identity of that type, the value that must survive)
#
# Each row is one arrow docs/decode.md forbids, aimed at the field type that
# would have to perform it. The type check in the test is what makes the row
# bite: `"1" == "1"` proves nothing, `type(got) is str` proves everything.
_NO_COERCION_PROBES = [
    # "1" ──▶ int, and the other readings of a number an int field might attempt
    ("numeric_string_never_becomes_int", int, "int", "1"),
    ("padded_numeric_string_never_becomes_int", int, "int", "007"),
    ("whole_float_never_becomes_int", int, "int", 1.0),
    ("true_never_becomes_int", int, "int", True),
    ("int_subclass_never_becomes_int", int, "int", _MyInt(1)),

    # "1.0" / "1.5" ──▶ float. (`1 ──▶ 1.0` is a restoration, not a coercion,
    # and belongs to the catalogue, not here.)
    ("decimal_string_never_becomes_float", float, "float", "1.0"),
    ("fractional_string_never_becomes_float", float, "float", "1.5"),
    ("bool_never_becomes_float", float, "float", True),
    ("float_subclass_never_becomes_float", float, "float", _MyFloat(1.5)),

    # 1 ──▶ "1", and everything else a str field must refuse to spell
    ("int_never_becomes_str", str, "str", 1),
    ("float_never_becomes_str", str, "str", 1.0),
    ("bool_never_becomes_str", str, "str", True),
    ("none_never_becomes_str", str, "str", None),
    ("str_subclass_never_becomes_str", str, "str", _MyStr("x")),
    ("path_never_becomes_str", str, "str", Path("a.txt")),
    ("date_looking_text_stays_str", str, "str", "2026-08-08"),
    ("time_looking_text_stays_str", str, "str", "14:30"),
    ("enum_name_looking_text_stays_str", str, "str", "ADMIN"),
    ("empty_string_never_becomes_none_under_str", str, "str", ""),
    ("null_text_never_becomes_none_under_str", str, "str", "null"),
    ("none_text_never_becomes_none_under_str", str, "str", "None"),

    # "true"/"false"/"True" ──▶ bool, and 1 ──▶ True, 0 ──▶ False
    ("lowercase_true_never_becomes_bool", bool, "bool", "true"),
    ("lowercase_false_never_becomes_bool", bool, "bool", "false"),
    ("capitalised_true_never_becomes_bool", bool, "bool", "True"),
    ("one_string_never_becomes_bool", bool, "bool", "1"),
    ("empty_string_never_becomes_bool", bool, "bool", ""),
    ("one_never_becomes_true", bool, "bool", 1),
    ("zero_never_becomes_false", bool, "bool", 0),
    ("float_never_becomes_bool", bool, "bool", 1.0),

    # a datetime ──▶ date, and every non-canonical spelling of a day
    ("datetime_never_becomes_date", date, "date", datetime(2026, 8, 8, 10, 0)),
    ("compact_digits_never_become_date", date, "date", "20260808"),
    ("slashed_text_never_becomes_date", date, "date", "2026/08/08"),
    ("iso_week_never_becomes_date", date, "date", "2026-W32-6"),
    ("timestamp_text_never_becomes_date", date, "date", "2026-08-08T10:00"),
    ("unreal_day_never_becomes_date", date, "date", "2026-02-31"),
    ("ordinal_int_never_becomes_date", date, "date", 20260808),
    ("empty_string_never_becomes_date", date, "date", ""),

    # the Time grammar, kept disjoint from the Date one
    ("compact_digits_never_become_time", time, "time", "1430"),
    ("bare_four_digits_never_become_time", time, "time", "2020"),
    ("seconds_since_midnight_never_become_time", time, "time", 52200),
    ("dashed_text_never_becomes_time", time, "time", "2026-08-08"),

    # enums travel by member name; nothing else reads as one
    ("member_value_never_becomes_enum", _Role, "_Role", "admin"),
    ("member_index_never_becomes_enum", _Role, "_Role", 0),
    ("unknown_name_never_becomes_enum", _Role, "_Role", "GUEST"),
    ("lowercased_name_never_becomes_enum", _Role, "_Role", "admin "),
    ("null_text_never_becomes_none_under_enum", _Role, "_Role", "null"),

    # "[]" ──▶ list, tuple ──▶ list, set ──▶ list
    ("bracket_string_never_becomes_list", list[int], "list[int]", "[]"),
    ("csv_string_never_becomes_list", list[int], "list[int]", "1,2"),
    ("tuple_never_becomes_list", list[int], "list[int]", (1, 2)),
    ("set_never_becomes_list", list[int], "list[int]", {1, 2}),
    ("frozenset_never_becomes_list", list[int], "list[int]", frozenset({1, 2})),
    ("range_never_becomes_list", list[int], "list[int]", range(2)),
    ("none_never_becomes_empty_list", list[int], "list[int]", None),

    # a dataclass arrives as a dict; nothing else is turned into one
    ("instance_never_becomes_dict", _Point, "_Point", _Point(x=1)),
    ("list_never_becomes_struct", _Point, "_Point", [1]),
    ("string_never_becomes_struct", _Point, "_Point", "x"),

    # "null" / "None" / "" ──▶ None, tried against the option that would take it
    ("null_text_never_becomes_none", int | None, "int | None", "null"),
    ("none_text_never_becomes_none", int | None, "int | None", "None"),
    ("empty_string_never_becomes_none", int | None, "int | None", ""),
    ("zero_never_becomes_none", int | None, "int | None", 0),
]


@pytest.mark.parametrize("depth", _DEPTHS, ids=_DEPTHS)
@pytest.mark.parametrize(
    "probe_id, field_type, option_id, hostile",
    _NO_COERCION_PROBES,
    ids=[probe[0] for probe in _NO_COERCION_PROBES],
)
def test_decode_hands_the_value_back_exactly_as_it_came(
        depth, probe_id, field_type, option_id, hostile):
    """docs/decode.md, '`decode` is not coercion': the exact type survives too.

    Equality is not enough — `True == 1` and `1 == 1.0` — so the assertion is on
    `type(...) is type(...)`, which is also what docs/philosophy.md, 'Hints are
    exact', promises validation will check afterwards.
    """
    schema, data, read = _placed(depth, field_type, option_id, hostile)

    got = read(schema.decode(data))

    assert type(got) is type(hostile), f"{probe_id} at {depth}: type changed"
    assert got == hostile, f"{probe_id} at {depth}: value changed"


@pytest.mark.parametrize("depth", _DEPTHS, ids=_DEPTHS)
@pytest.mark.parametrize(
    "probe_id, field_type, option_id, hostile",
    _NO_COERCION_PROBES,
    ids=[probe[0] for probe in _NO_COERCION_PROBES],
)
def test_decode_of_a_hostile_value_raises_no_schema_error(
        depth, probe_id, field_type, option_id, hostile):
    """docs/decode.md: 'Decode never raises a schema error.'"""
    schema, data, _read = _placed(depth, field_type, option_id, hostile)

    try:
        schema.decode(data)
    except (SchemaTypeError, SchemaValueError) as error:  # pragma: no cover
        pytest.fail(f"{probe_id} at {depth}: decode diagnosed the value: {error}")


_RESTORATIONS = [
    ("date", date, "date", "2026-08-08", date(2026, 8, 8)),
    ("time", time, "time", "14:30", time(14, 30)),
    ("time_with_seconds", time, "time", "14:30:00", time(14, 30)),
    ("enum", _Role, "_Role", "ADMIN", _Role.ADMIN),
    ("whole_float", float, "float", 3, 3.0),
]


@pytest.mark.parametrize("depth", _DEPTHS, ids=_DEPTHS)
@pytest.mark.parametrize(
    "probe_id, field_type, option_id, portable, expected",
    _RESTORATIONS,
    ids=[probe[0] for probe in _RESTORATIONS],
)
def test_every_depth_of_the_battery_reaches_a_shape_that_does_decode(
        depth, probe_id, field_type, option_id, portable, expected):
    """The positive control for the battery above.

    docs/decode.md: '`decode` restores those four and does nothing else.' If a
    depth in `_placed` built a schema decode never descended into, every
    no-coercion row would pass for the wrong reason. These five rows prove each
    depth is live.
    """
    schema, data, read = _placed(depth, field_type, option_id, portable)

    got = read(schema.decode(data))

    assert type(got) is type(expected), f"{probe_id} at {depth}: not restored"
    assert got == expected


def test_a_str_field_holding_a_date_spelling_stays_a_str():
    """docs/decode.md: 'The shape decides the reading; the text never does.'"""
    @dataclass
    class Post:
        slug: str

    assert struct_of(Post).decode({"slug": "2026-08-08"}) == {"slug": "2026-08-08"}
    assert type(struct_of(Post).decode({"slug": "2026-08-08"})["slug"]) is str


def test_signature_decode_draws_the_same_line_as_struct_decode():
    """docs/decode.md: '`Struct.decode(data)` and `Signature.decode(kwargs)`' share one operation."""
    def run(n: int, day: date, flag: bool):
        ...

    decoded = signature_of(run).decode({"n": "1", "day": "2026-08-08", "flag": "true"})

    assert decoded == {"n": "1", "day": date(2026, 8, 8), "flag": "true"}
    assert type(decoded["n"]) is str
    assert type(decoded["flag"]) is str


# =========================================================================
# 2. Idempotence
# =========================================================================

_IDEMPOTENCE_INPUTS = [
    ("portable_wire_tree", _WIRE),
    ("already_exact_tree", _EXACT),
    ("empty_dict", {}),
    ("partial_tree", {"n": 1, "day": "2026-08-08"}),
    ("unknown_keys_only", {"nope": {"deep": ["1", "true"]}}),
    ("hostile_scalars", {"n": "1", "ratio": "1.5", "active": "true", "day": "hello",
                         "at": "1430", "role": "admin", "maybe": "null"}),
    ("hostile_containers", {"items": "[]", "matrix": [["20260808"], "x"],
                            "inner": ["not", "a", "dict"]}),
    ("malformed_wrapper_missing_type", {"choice": {"$value": "2026-08-08"}}),
    ("malformed_wrapper_unknown_type", {"choice": {"$type": "nope", "$value": "x"}}),
    ("malformed_wrapper_extra_key", {"choice": {"$type": "date", "$value": "2026-08-08",
                                                "extra": 1}}),
    ("wrapper_whose_payload_missed", {"choice": {"$type": "date", "$value": "nonsense"}}),
    ("nested_wrapper", {"choice": {"$type": "date",
                                   "$value": {"$type": "date", "$value": "2026-08-08"}}}),
    ("kept_wrapper", {"either": {"$type": "list[int]", "$value": [1, 2]}}),
    ("non_dict_root_none", None),
    ("non_dict_root_list", [1, 2]),
    ("non_dict_root_str", "x"),
]


@pytest.mark.parametrize(
    "data", [entry[1] for entry in _IDEMPOTENCE_INPUTS],
    ids=[entry[0] for entry in _IDEMPOTENCE_INPUTS],
)
def test_decode_is_idempotent(data):
    """docs/decode.md, 'Order': 'nothing in an exact tree matches a portable spelling that isn't already its own'.

    A second pass therefore has nothing left to do — including over a tree that
    already carries real `date`, `time` and enum objects.
    """
    once = _SCHEMA.decode(data)
    twice = _SCHEMA.decode(once)
    thrice = _SCHEMA.decode(twice)

    assert twice == once
    assert thrice == once
    assert _types_of(twice) == _types_of(once)
    assert _types_of(thrice) == _types_of(once)


@pytest.mark.parametrize("depth", _DEPTHS, ids=_DEPTHS)
@pytest.mark.parametrize(
    "probe_id, field_type, option_id, hostile",
    _NO_COERCION_PROBES,
    ids=[probe[0] for probe in _NO_COERCION_PROBES],
)
def test_decode_is_idempotent_over_the_no_coercion_battery(
        depth, probe_id, field_type, option_id, hostile):
    """docs/decode.md, 'Order': a value decode left alone stays left alone."""
    schema, data, read = _placed(depth, field_type, option_id, hostile)

    once = schema.decode(data)
    twice = schema.decode(once)

    assert _types_of(twice) == _types_of(once)
    assert type(read(twice)) is type(hostile)
    assert read(twice) == hostile


def test_decoding_an_already_decoded_tree_leaves_the_real_objects_in_place():
    """docs/decode.md, 'Order': 'resolve fills absent keys with real Python objects [...] decoding them again would be meaningless'."""
    once = _SCHEMA.decode(_WIRE)
    twice = _SCHEMA.decode(once)

    assert twice["day"] == date(2026, 8, 8)
    assert twice["at"] == time(14, 30)
    assert twice["role"] is _Role.ADMIN
    assert twice["choice"] == date(2026, 8, 8)
    assert twice["matrix"] == [[date(2026, 8, 8)], []]
    assert twice["inner"]["when"] == date(2000, 1, 1)


# =========================================================================
# 3. build does not depend on decode
# =========================================================================


def test_build_takes_an_exact_tree_without_decode():
    """docs/decode.md, 'Order': 'For a value already in exact Python [...] `decode` is unnecessary and `build` takes it directly'."""
    built = _SCHEMA.build(_EXACT)

    assert built.day == date(2026, 8, 8)
    assert built.role is _Role.ADMIN
    assert built.inner == _Inner(when=date(2000, 1, 1), tags=["1", "true"])


def test_decoding_an_exact_tree_is_harmless_and_build_agrees():
    """docs/decode.md, 'Order': 'Decoding it is harmless'."""
    assert _SCHEMA.decode(_EXACT) == _EXACT
    assert _types_of(_SCHEMA.decode(_EXACT)) == _types_of(_EXACT)
    assert _SCHEMA.build(_EXACT) == _SCHEMA.build(_SCHEMA.decode(_EXACT))


def test_the_pipeline_and_the_direct_build_reach_the_same_instance():
    """docs/decode.md: '`schema.build(schema.decode(data))`' — one direction, one result."""
    assert _SCHEMA.build(_SCHEMA.decode(_WIRE)) == _SCHEMA.build(_EXACT)


@pytest.mark.parametrize(
    "exact_value, hint",
    [
        (5, int),
        (1.5, float),
        ("hi", str),
        (True, bool),
        (date(2026, 8, 8), date),
        (time(14, 30), time),
        (_Role.ADMIN, _Role),
        ([1, 2], list[int]),
        ([[date(2026, 8, 8)]], list[list[date]]),
        (None, int | None),
    ],
    ids=["int", "float", "str", "bool", "date", "time", "enum", "list",
         "nested_list", "none_option"],
)
def test_build_of_an_exact_value_matches_build_of_its_decoded_self(exact_value, hint):
    """docs/decode.md, 'Order': there is no value in an exact tree that decode changes for build."""
    cls = make_dataclass("_Root", [("x", hint)])
    schema = struct_of(cls)
    data = {"x": exact_value}

    assert schema.build(data) == schema.build(schema.decode(data))


def test_signature_build_takes_an_exact_kwargs_tree_without_decode():
    """docs/decode.md: `Signature.decode(kwargs)` sits beside `Signature.build`, never inside it."""
    def run(day: date, role: _Role):
        ...

    sig = signature_of(run)
    exact = {"day": date(2026, 8, 8), "role": _Role.ADMIN}

    assert sig.build(exact) == exact
    assert sig.build(exact) == sig.build(sig.decode(exact))


# =========================================================================
# 4. decode does not fill defaults
# =========================================================================


def test_decode_leaves_a_simple_default_key_absent_and_resolve_fills_it():
    """docs/decode.md, 'What decode leaves alone': 'Absent keys stay absent. [...] Decode never runs a recipe.'"""
    @dataclass
    class C:
        n: int = 7

    schema = struct_of(C)

    assert schema.decode({}) == {}
    assert "n" not in schema.decode({})
    assert schema.resolve({}) == {"n": 7}
    assert schema.build({}) == C(n=7)


def test_decode_leaves_a_factory_default_key_absent():
    """docs/decode.md: 'Filling a missing key is what a default is for, and `resolve` serves it'."""
    @dataclass
    class C:
        xs: list[int] = field(default_factory=lambda: [1, 2])

    schema = struct_of(C)

    assert schema.decode({}) == {}
    assert schema.resolve({}) == {"xs": [1, 2]}


def test_decode_leaves_a_default_inside_a_union_absent():
    """docs/decode.md: an option is not a value, and decode supplies neither."""
    @dataclass
    class C:
        maybe: int | None = None
        choice: str | date = "unset"

    schema = struct_of(C)

    assert schema.decode({}) == {}
    assert schema.resolve({}) == {"maybe": None, "choice": "unset"}


def test_decode_leaves_a_nested_dataclass_default_absent_at_every_depth():
    """docs/decode.md: 'resolve serves it — fresh, certified, at its own depth'."""
    @dataclass
    class Leaf:
        size: int = 20

    @dataclass
    class Middle:
        leaf: Leaf = field(default_factory=Leaf)

    @dataclass
    class Root:
        middle: Middle = field(default_factory=Middle)

    schema = struct_of(Root)

    assert schema.decode({}) == {}
    assert schema.decode({"middle": {}}) == {"middle": {}}
    assert schema.decode({"middle": {"leaf": {}}}) == {"middle": {"leaf": {}}}
    assert schema.build({}) == Root(middle=Middle(leaf=Leaf(size=20)))


@pytest.mark.parametrize("data", [{}, {"other": 1}, {"xs": [1]}],
                         ids=["empty", "unknown_key_only", "key_present"])
def test_decode_never_runs_a_default_factory(data):
    """docs/decode.md, 'What decode leaves alone': 'Decode never runs a recipe.'

    The counter starts at 1: docs/defaults.md certifies the recipe once when the
    schema compiles. Every decode after that must leave it exactly there.
    """
    calls = []

    def make():
        calls.append(1)
        return [len(calls)]

    @dataclass
    class C:
        xs: list[int] = field(default_factory=make)

    schema = struct_of(C)
    assert len(calls) == 1                 # certification, at compile time

    for _ in range(5):
        schema.decode(data)

    assert len(calls) == 1                 # five decodes, not one recipe run

    schema.resolve({})
    assert len(calls) == 2                 # resolve is the one that serves it


def test_decode_never_runs_a_nested_constructor_recipe():
    """docs/decode.md: a dataclass default is a recipe too, and decode does not run it."""
    counter = {"n": 0}

    @dataclass
    class Opt:
        def __post_init__(self):
            counter["n"] += 1

    @dataclass
    class C:
        opt: Opt = field(default_factory=Opt)

    schema = struct_of(C)
    assert counter["n"] == 1

    schema.decode({})
    schema.decode({"opt": {}})

    assert counter["n"] == 1


def test_signature_decode_leaves_defaulted_arguments_absent():
    """docs/decode.md: `Signature.decode` follows the same rule for parameter defaults."""
    def run(n: int = 3, tags: list[str] = []):
        ...

    sig = signature_of(run)

    assert sig.decode({}) == {}
    assert sig.resolve({}) == {"n": 3, "tags": []}


# =========================================================================
# 5. decode does not validate
# =========================================================================

_VIOLATIONS = [
    ("min", Annotated[int, Min(0)], -5),
    ("max", Annotated[int, Max(10)], 99),
    ("pattern", Annotated[str, Pattern(r"^[a-z]+$")], "ABC123"),
    ("choices", Annotated[str, Choices(values=("fast", "safe"))], "slow"),
    ("multiple_of", Annotated[int, MultipleOf(5)], 7),
    ("file_hint_extension", Annotated[str, FileHint(extensions=(".png",))],
     "image.gif"),
    ("wrong_type_for_int", int, "1"),
    ("wrong_type_for_bool", bool, 1),
    ("unreal_date", date, "2026-02-31"),
    ("aware_time", time, "10:00:00+02:00"),
    ("subsecond_time", time, "10:00:00.5"),
    ("unknown_enum_name", _Role, "GUEST"),
    ("list_spelled_as_text", list[int], "[]"),
    ("struct_spelled_as_list", _Point, [1]),
    ("min_inside_a_list", list[Annotated[int, Min(0)]], [-1]),
]


@pytest.mark.parametrize(
    "hint, value", [(entry[1], entry[2]) for entry in _VIOLATIONS],
    ids=[entry[0] for entry in _VIOLATIONS],
)
def test_decode_passes_a_violating_value_through_and_build_reports_it(hint, value):
    """docs/decode.md: 'Decode never raises a schema error. It has no opinion about whether a value is acceptable — that is `resolve` and `build`.'"""
    cls = make_dataclass("_Root", [("x", hint)])
    schema = struct_of(cls)
    data = {"x": value}

    schema.decode(data)          # no exception, of any kind

    with pytest.raises((SchemaTypeError, SchemaValueError)):
        schema.build(schema.decode(data))


_HOSTILE_TREES = [
    ("wrong_type_everywhere", {"n": "1", "ratio": "x", "name": 1, "active": "true",
                               "day": 0, "at": [], "role": {}, "items": "no",
                               "matrix": 1, "inner": 2, "choice": [], "either": 3,
                               "maybe": "null"}),
    ("nested_junk", {"inner": {"when": ["2026-08-08"], "tags": {"a": 1}}}),
    ("list_of_junk", {"items": [None, "1", [], {}, True]}),
    ("matrix_of_junk", {"matrix": [None, "x", [1], [{"$type": "date"}]]}),
    ("struct_instance_inside", {"inner": _Inner(when=date(2026, 8, 8), tags=[])}),
    ("wrapper_everywhere", {"n": {"$type": "int", "$value": 1},
                            "choice": {"$type": "str", "$value": 1},
                            "either": {"$type": "list[float]", "$value": []}}),
    ("wrapper_with_non_string_type", {"choice": {"$type": 1, "$value": "x"}}),
    ("wrapper_missing_value", {"choice": {"$type": "date"}}),
    ("unknown_keys", {"nope": 1, "$type": "Whatever", "$value": None}),
    ("empty", {}),
    ("deeply_absurd", {"matrix": [[["2026-08-08"]]], "items": [[1]], "role": ["ADMIN"]}),
]


@pytest.mark.parametrize(
    "tree", [entry[1] for entry in _HOSTILE_TREES],
    ids=[entry[0] for entry in _HOSTILE_TREES],
)
def test_decode_never_raises_a_schema_error(tree):
    """docs/decode.md: 'Decode never raises a schema error.'

    docs/philosophy.md, 'Validation fails fast': the one coordinate and the one
    reason belong to `resolve`/`build`. 'One failure, reported once, in one
    place.'
    """
    try:
        _SCHEMA.decode(tree)
    except (SchemaTypeError, SchemaValueError) as error:  # pragma: no cover
        pytest.fail(f"decode diagnosed the tree: {error}")


@pytest.mark.parametrize(
    "tree", [entry[1] for entry in _HOSTILE_TREES],
    ids=[entry[0] for entry in _HOSTILE_TREES],
)
def test_decode_of_a_hostile_tree_is_still_idempotent(tree):
    """docs/decode.md: a tree decode could not read is a tree decode cannot read twice."""
    once = _SCHEMA.decode(tree)

    assert _types_of(_SCHEMA.decode(once)) == _types_of(once)


def test_decode_does_not_diagnose_a_malformed_wrapper_build_does():
    """docs/decode.md, 'Unions': 'Malformed wrappers [...] are all handed back untouched [...] Decode never reproduces that diagnosis.'"""
    @dataclass
    class Query:
        when: str | date

    schema = struct_of(Query)
    data = {"when": {"$type": "date", "$value": "nonsense"}}

    assert schema.decode(data) == {"when": {"$type": "date", "$value": "nonsense"}}

    with pytest.raises(SchemaTypeError) as error:
        schema.build(schema.decode(data))

    assert str(error.value) == "when: expected str | date, got dict"


# =========================================================================
# 6. Keys
# =========================================================================


def test_an_unknown_key_travels_through_untouched_and_build_reports_it():
    """docs/decode.md: 'Unknown keys travel through untouched [...] Dropping them here would turn a rejected payload into an accepted one.'"""
    schema = struct_of(_Point)
    data = {"x": 1, "unknown": 2}

    assert schema.decode(data) == {"x": 1, "unknown": 2}

    with pytest.raises(SchemaTypeError) as error:
        schema.build(schema.decode(data))

    assert str(error.value) == "unexpected key(s): unknown"


@pytest.mark.parametrize(
    "unknown_value",
    ["2026-08-08", "14:30", "ADMIN", 1, True, None, ["2026-08-08"],
     {"nested": "2026-08-08"}, {"$type": "date", "$value": "2026-08-08"}],
    ids=["date_text", "time_text", "enum_name", "int", "bool", "none",
         "list_of_date_text", "nested_dict", "wrapper"],
)
def test_an_unknown_key_keeps_its_value_verbatim(unknown_value):
    """docs/decode.md: an unknown key has no shape, so nothing decides a reading for it."""
    schema = struct_of(_Point)

    decoded = schema.decode({"unknown": unknown_value})

    assert decoded == {"unknown": unknown_value}
    assert _types_of(decoded) == _types_of({"unknown": unknown_value})


def test_unknown_keys_are_reported_together_by_build_after_decode():
    """docs/decode.md: decode preserves exactly what `resolve` needs to name."""
    schema = struct_of(_Point)

    with pytest.raises(SchemaTypeError) as error:
        schema.build(schema.decode({"x": 1, "b": 2, "a": 3}))

    assert str(error.value) == "unexpected key(s): a, b"


def test_an_unknown_argument_survives_signature_decode():
    """docs/decode.md: the rule is the same for `Signature.decode(kwargs)`."""
    def run(n: int):
        ...

    sig = signature_of(run)

    assert sig.decode({"n": 1, "nope": "x"}) == {"n": 1, "nope": "x"}

    with pytest.raises(SchemaTypeError) as error:
        sig.build(sig.decode({"n": 1, "nope": "x"}))

    assert str(error.value) == "unexpected argument(s): nope"


@pytest.mark.parametrize(
    "key, reported",
    [(1, "int"), (True, "bool"), ((1, 2), "tuple"), (None, "NoneType"), (1.5, "float")],
    ids=["int", "bool", "tuple", "none", "float"],
)
def test_a_non_string_key_survives_decode_and_build_reports_it(key, reported):
    """docs/decode.md: decode does not diagnose, so a key it cannot name is a key it keeps."""
    schema = struct_of(_Point)
    data = {key: "2026-08-08"}

    decoded = schema.decode(data)

    assert decoded == data
    assert list(decoded) == [key]
    assert type(next(iter(decoded))) is type(key)

    with pytest.raises(SchemaTypeError) as error:
        schema.build(decoded)

    assert str(error.value) == f"expected string keys, got {reported}"


def test_a_non_string_key_survives_at_depth():
    """docs/decode.md: the rule holds inside a nested dataclass, not only at the root."""
    @dataclass
    class Root:
        point: _Point

    decoded = struct_of(Root).decode({"point": {1: "a", "x": "1"}})

    assert decoded == {"point": {1: "a", "x": "1"}}

    with pytest.raises(SchemaTypeError) as error:
        struct_of(Root).build(decoded)

    assert str(error.value) == "point: expected string keys, got int"


# =========================================================================
# 7. A root that is not a dict
# =========================================================================

_BAD_ROOTS = [
    ("none", None),
    ("empty_list", []),
    ("list", [1, 2]),
    ("str", "x"),
    ("int", 5),
    ("float", 3.0),
    ("bool", True),
    ("tuple", (1, 2)),
    ("instance", _Point(x=1)),
]


@pytest.mark.parametrize("root", [entry[1] for entry in _BAD_ROOTS],
                         ids=[entry[0] for entry in _BAD_ROOTS])
def test_a_root_that_is_not_a_dict_comes_back_as_it_came(root):
    """docs/decode.md, 'What decode leaves alone': 'A root that is not a dict — None, a list, a string, a number, a dataclass instance — is returned as it came'."""
    decoded = struct_of(_Point).decode(root)

    assert decoded == root
    assert type(decoded) is type(root)


@pytest.mark.parametrize("root", [entry[1] for entry in _BAD_ROOTS],
                         ids=[entry[0] for entry in _BAD_ROOTS])
def test_build_is_the_one_that_reports_a_root_that_is_not_a_dict(root):
    """docs/decode.md: '[...] and `build` reports it.'"""
    schema = struct_of(_Point)

    with pytest.raises(SchemaTypeError):
        schema.build(schema.decode(root))


def test_a_dataclass_instance_root_is_handed_back_by_reference():
    """docs/decode.md: an instance is not a container decode rebuilds — it is not portable data at all."""
    instance = _Point(x=1)

    assert struct_of(_Point).decode(instance) is instance

    with pytest.raises(SchemaTypeError) as error:
        struct_of(_Point).build(instance)

    assert str(error.value) == "expected dict, got _Point instance"


@pytest.mark.parametrize("root", [entry[1] for entry in _BAD_ROOTS],
                         ids=[entry[0] for entry in _BAD_ROOTS])
def test_signature_decode_returns_a_bad_root_as_it_came(root):
    """docs/decode.md: `Signature.decode(kwargs)` answers the same way."""
    def run(n: int):
        ...

    assert signature_of(run).decode(root) == root


# =========================================================================
# 8. Fresh trees
# =========================================================================

_FRESHNESS_TREES = [
    ("wire", _WIRE),
    ("exact", _EXACT),
    ("hostile", {"n": "1", "items": ["1"], "matrix": [["x"], []],
                 "inner": {"when": "hello", "tags": []}, "nope": {"deep": [{"a": [1]}]}}),
    ("empty_containers", {"items": [], "matrix": [[]], "inner": {}, "nope": {}}),
    ("unknown_subtree", {"nope": {"a": [{"b": [{"c": []}]}]}}),
    ("kept_wrapper", {"either": {"$type": "list[str]", "$value": ["a", "b"]}}),
    ("malformed_wrapper", {"choice": {"$type": "date", "$value": "nonsense"}}),
]


@pytest.mark.parametrize("tree", [entry[1] for entry in _FRESHNESS_TREES],
                         ids=[entry[0] for entry in _FRESHNESS_TREES])
def test_decode_never_modifies_the_tree_it_is_given(tree):
    """docs/decode.md, 'Fresh trees': '`decode` never modifies the tree it is given'."""
    before = copy.deepcopy(tree)

    _SCHEMA.decode(tree)

    assert tree == before
    assert _types_of(tree) == _types_of(before)


@pytest.mark.parametrize("tree", [entry[1] for entry in _FRESHNESS_TREES],
                         ids=[entry[0] for entry in _FRESHNESS_TREES])
def test_no_container_in_the_result_is_a_container_from_the_input(tree):
    """docs/decode.md, 'Fresh trees': '[decode] never hands back a container from it. Every dict and list in the result is newly built'."""
    decoded = _SCHEMA.decode(tree)

    shared = _container_ids(tree) & _container_ids(decoded)

    assert shared == set(), f"{len(shared)} container(s) survived from the input"


def test_the_freshness_check_is_not_vacuous():
    """A guard for the guard: the id sets above only mean something if both trees hold containers.

    The two counts need not match. A consumed wrapper — docs/decode.md,
    'Unions' — removes one dict from the result, which is the point of consuming
    it.
    """
    decoded = _SCHEMA.decode(_WIRE)

    assert len(_container_ids(_WIRE)) >= 8
    assert len(_container_ids(decoded)) >= 8


def test_mutating_the_result_leaves_the_input_and_later_calls_alone():
    """docs/decode.md, 'Fresh trees': 'the caller may keep the input, modify the output, or both'."""
    wire = copy.deepcopy(_WIRE)
    first = _SCHEMA.decode(wire)

    first["items"].append(99)
    first["matrix"][0].clear()
    first["inner"]["tags"].append("mutated")
    first["either"]["$value"].append("mutated")
    first["new"] = "mutated"

    assert wire == _WIRE
    second = _SCHEMA.decode(wire)
    assert second["items"] == [1, 2]
    assert second["matrix"] == [[date(2026, 8, 8)], []]
    assert second["inner"]["tags"] == ["1", "true"]
    assert second["either"] == {"$type": "list[str]", "$value": ["a"]}
    assert "new" not in second


def test_mutating_the_input_afterwards_leaves_the_result_alone():
    """The other half of 'the caller may keep the input, modify the output, or both'."""
    wire = {"when": "2026-08-08", "tags": ["a"]}
    decoded = struct_of(_Inner).decode(wire)

    wire["tags"].append("b")
    wire["when"] = "1999-01-01"

    assert decoded == {"when": date(2026, 8, 8), "tags": ["a"]}


def test_aliasing_is_not_preserved_for_dicts():
    """docs/decode.md, 'Fresh trees': 'one dict referenced twice in the input becomes two independent dicts in the output'."""
    shared = {"x": 1}
    decoded = struct_of(_Pair).decode({"left": shared, "right": shared})

    assert decoded == {"left": {"x": 1}, "right": {"x": 1}}
    assert decoded["left"] is not decoded["right"]
    assert decoded["left"] is not shared
    assert decoded["right"] is not shared

    decoded["left"]["x"] = 99

    assert decoded["right"] == {"x": 1}
    assert shared == {"x": 1}


def test_aliasing_is_not_preserved_for_lists():
    """docs/decode.md, 'Fresh trees': 'A portable tree has no aliases to carry'."""
    shared = ["a"]
    decoded = struct_of(_Lists).decode({"one": shared, "two": shared})

    assert decoded == {"one": ["a"], "two": ["a"]}
    assert decoded["one"] is not decoded["two"]
    assert decoded["one"] is not shared


def test_aliasing_is_not_preserved_inside_a_single_list():
    """The same list object twice inside one list is two lists out."""
    @dataclass
    class Rows:
        rows: list[list[str]]

    shared = ["a"]
    decoded = struct_of(Rows).decode({"rows": [shared, shared]})

    assert decoded["rows"] == [["a"], ["a"]]
    assert decoded["rows"][0] is not decoded["rows"][1]


def test_an_unknown_subtree_is_copied_not_shared():
    """docs/decode.md, 'Fresh trees': the promise is about every container, including ones no shape claims."""
    unknown = {"deep": [{"deeper": []}]}
    decoded = struct_of(_Point).decode({"unknown": unknown})

    assert decoded == {"unknown": {"deep": [{"deeper": []}]}}
    assert decoded["unknown"] is not unknown
    assert decoded["unknown"]["deep"] is not unknown["deep"]
    assert decoded["unknown"]["deep"][0] is not unknown["deep"][0]


def test_signature_decode_hands_back_fresh_containers_too():
    """docs/decode.md: 'Fresh trees' is a property of the operation, not of `Struct`."""
    def run(tags: list[str], point: _Point):
        ...

    kwargs = {"tags": ["a"], "point": {"x": 1}}
    decoded = signature_of(run).decode(kwargs)

    assert _container_ids(kwargs) & _container_ids(decoded) == set()


# =========================================================================
# 9. Cyclic input data
# =========================================================================


def test_a_self_containing_unknown_subtree_raises_recursion_error():
    """docs/decode.md, 'Fresh trees': 'Cyclic input data raises RecursionError, as it does everywhere else in the core'.

    docs/restrictions.md, 'Cyclic input data': 'The error propagates raw.'
    """
    data: dict = {}
    data["unknown"] = data

    with pytest.raises(RecursionError):
        struct_of(_Point).decode(data)


def test_a_self_containing_dataclass_payload_raises_recursion_error():
    """docs/restrictions.md, 'Cyclic input data' — through a field decode actually descends into."""
    data: dict = {}
    data["child"] = data

    with pytest.raises(RecursionError):
        struct_of(_Node).decode(data)


def test_a_self_containing_list_raises_recursion_error():
    """docs/restrictions.md, 'Cyclic input data' — a list is a container decode rebuilds too."""
    @dataclass
    class Rows:
        rows: list[list[str]]

    rows: list = []
    rows.append(rows)

    with pytest.raises(RecursionError):
        struct_of(Rows).decode({"rows": rows})


def test_a_cycle_is_not_reported_as_a_schema_error():
    """docs/restrictions.md: 'Tracking visited containers on every call would charge all real inputs for a cycle that ordinary serialized data cannot contain'."""
    data: dict = {}
    data["unknown"] = data

    with pytest.raises(RecursionError) as error:
        struct_of(_Point).decode(data)

    assert not isinstance(error.value, (SchemaTypeError, SchemaValueError))


# =========================================================================
# 10. Cost
# =========================================================================


@dataclass
class _Calendar:
    days: list[date]


def _iso_days(size: int) -> list[str]:
    """`size` canonical `YYYY-MM-DD` spellings, all of them real days."""
    return [f"2020-{1 + index % 12:02d}-{1 + index % 28:02d}" for index in range(size)]


@pytest.mark.slow
@pytest.mark.parametrize("size", [1_000, 50_000], ids=["small", "large"])
def test_a_large_flat_list_decodes_without_blowing_up(size):
    """docs/comparison.md, 'Cost': the work is linear in the size of the input.

    The assertion is structural, never a wall-clock reading: a quadratic decode
    would never finish this, and a lucky machine would never make a timing
    assertion mean anything.
    """
    wire = {"days": _iso_days(size)}

    decoded = struct_of(_Calendar).decode(wire)

    assert len(decoded["days"]) == size
    assert set(map(type, decoded["days"])) == {date}
    assert decoded["days"][0] == date(2020, 1, 1)
    assert decoded["days"] == [date.fromisoformat(text) for text in wire["days"]]


@pytest.mark.slow
def test_a_large_list_of_undecodable_items_is_still_only_copied():
    """docs/decode.md: 'a value decode cannot restore is handed back exactly as it came' — at scale, and still fresh."""
    wire = {"days": ["not-a-date"] * 50_000}

    decoded = struct_of(_Calendar).decode(wire)

    assert len(decoded["days"]) == 50_000
    assert set(map(type, decoded["days"])) == {str}
    assert decoded["days"] is not wire["days"]

"""Adversarial hardening of `decode()` — release audit (agent B).

Every test here was written against a falsification attempt: a concrete portable
tree that `docs/decode.md` promises something about, fed to `Struct.decode` /
`Signature.decode` and checked with a type-sensitive oracle. Three were real
divergences from the documented contract and were pinned as such until they were
fixed; the rest lock in the invariants that survived roughly half a million
generated probes (see the report accompanying this file).
"""
import copy
from dataclasses import dataclass, make_dataclass
from datetime import date, time
from enum import Enum

import pytest
from hypothesis import given, settings, strategies as st

from pytypehint import SchemaTypeError, SchemaValueError, signature_of, struct_of


class Role(Enum):
    ADMIN = "admin"
    USER = "user"


class Status(Enum):
    OPEN = "open"
    SHUT = "shut"


def _schema_for(annotation, name="x"):
    """A one-field dataclass schema, so a shape can be probed on its own."""
    cls = make_dataclass("Probe", [(name, annotation)])
    return struct_of(cls)


# ==========================================================================
# 1. B-01 — `Float` restores an int that no float is equal to
#
# docs/decode.md: "a whole float may arrive as `3` rather than `3.0`" and "a
# value decode cannot restore is handed back exactly as it came".  An int past
# 2**53 is not a whole float that lost its fraction — no float equals it — so
# there is nothing to restore, exactly as for an int past the float range, which
# `decode` already hands back.  Today the magnitude guard exists (OverflowError)
# but the exactness one does not, so the value is silently replaced by a
# neighbour and `build` accepts the neighbour.
# ==========================================================================
_INEXACT_INTS = [2**53 + 1, 2**53 + 3, -(2**53 + 1), 10**23, 10**308]


@pytest.mark.parametrize("wire", _INEXACT_INTS, ids=repr)
def test_an_int_no_float_equals_is_handed_back(wire):
    decoded = _schema_for(float).decode({"x": wire})["x"]
    assert decoded is wire


def test_build_reports_an_int_no_float_equals_instead_of_rounding_it():
    schema = _schema_for(float)

    with pytest.raises(SchemaTypeError) as error:
        schema.build(schema.decode({"x": 2**53 + 1}))
    assert str(error.value) == "x: expected float, got int"


def test_the_exactness_hole_is_not_only_at_the_top_level():
    wire = 2**53 + 1
    assert _schema_for(list[float]).decode({"x": [wire]})["x"] == [wire]
    # The payload never reaches `float`, so docs/decode.md leaves the wrapper
    # alone rather than filing the value under the option beside it.
    wrapper = {"$type": "float", "$value": wire}
    assert _schema_for(int | float).decode({"x": wrapper})["x"] == wrapper


def test_the_magnitude_guard_that_does_exist_still_holds():
    """The neighbouring case decode does get right, kept as a fence for the fix."""
    schema = _schema_for(float)
    huge = 10**400

    assert schema.decode({"x": huge})["x"] is huge
    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": huge})
    assert str(error.value) == "x: expected float, got int"


@pytest.mark.parametrize("wire", [0, 3, -7, 2**53, 2**53 + 2, 10**15], ids=repr)
def test_an_int_a_float_equals_exactly_is_restored(wire):
    """These are whole floats that lost their fraction, and must keep decoding."""
    decoded = _schema_for(float).decode({"x": wire})["x"]
    assert type(decoded) is float
    assert decoded == wire


# ==========================================================================
# 2. B-02 — a non-string key stops decoding at depth, but not at the root
#
# `_decode_dict` refuses to route a dict carrying a key it cannot name, so a
# nested dict with one is copied wholesale and nothing inside it is restored.
# `_decode_fields`, which serves the root, skips only that key and still decodes
# its siblings.  Both trees are rejected by `resolve` with the same message, so
# nothing unsafe follows; the two depths simply do not answer the same way, and
# docs/decode.md draws no such distinction.
# ==========================================================================
@dataclass
class _Inner:
    when: date


@dataclass
class _Outer:
    inner: _Inner
    when: date


def test_a_non_string_key_stops_decoding_at_depth_but_not_at_the_root():
    schema = struct_of(_Outer)

    root = schema.decode({1: "x", "when": "2026-08-08"})
    nested = schema.decode({"inner": {1: "x", "when": "2026-08-08"},
                            "when": "2026-08-08"})

    # At the root the sibling is still restored...
    assert root == {1: "x", "when": date(2026, 8, 8)}
    # ...one level down nothing inside that dict is, not even a sibling.
    assert nested == {"inner": {1: "x", "when": "2026-08-08"},
                      "when": date(2026, 8, 8)}

    # Either way validation reports the key.
    with pytest.raises(SchemaTypeError) as error:
        schema.build(root)
    assert str(error.value) == "expected string keys, got int"

    with pytest.raises(SchemaTypeError) as error:
        schema.build(nested)
    assert str(error.value) == "inner: expected string keys, got int"


def test_a_str_subclass_key_follows_the_same_root_rule():
    class MyStr(str):
        pass

    schema = struct_of(_Inner)
    decoded = schema.decode({MyStr("when"): "2026-08-08"})

    # The key is not exactly `str`, so the field is not named and not decoded,
    # while the key itself survives untouched for `resolve` to report.
    assert decoded == {"when": "2026-08-08"}
    assert type(next(iter(decoded))) is MyStr

    with pytest.raises(SchemaTypeError) as error:
        schema.build(decoded)
    assert str(error.value) == "expected string keys, got MyStr"


# ==========================================================================
# 3. B-03 — a zero fractional part is a non-canonical time that is accepted
#
# docs/decode.md pins the accepted spellings to `14:30` and `14:30:00` and
# explains the fractional part as admitted only so `Time` can report "time
# precision is limited to whole seconds".  With an all-zero fraction there is no
# rule left to report, so `HH:MM:SS.0*` travels the whole pipeline.
# ==========================================================================
@dataclass
class _Meeting:
    at: time


@pytest.mark.parametrize(
    "spelling",
    ["14:30:00.0", "14:30:00.00", "14:30:00.000", "14:30:00.000000"],
    ids=["1", "2", "3", "6"],
)
def test_a_zero_fraction_time_is_accepted_end_to_end(spelling):
    schema = struct_of(_Meeting)
    decoded = schema.decode({"at": spelling})["at"]

    assert decoded == time(14, 30)
    assert schema.build({"at": decoded}) == _Meeting(at=time(14, 30))


@pytest.mark.parametrize(
    "spelling, leaf",
    [("14:30:00.5", "at: time precision is limited to whole seconds: 14:30:00.500000"),
     ("14:30:00.000001", "at: time precision is limited to whole seconds: 14:30:00.000001"),
     ("14:30:00Z", "at: must be naive (no tzinfo): 14:30:00+00:00"),
     ("14:30:00+02:00", "at: must be naive (no tzinfo): 14:30:00+02:00")],
)
def test_a_non_zero_fraction_or_an_offset_reaches_the_shape_s_own_rule(spelling, leaf):
    """The documented reason the fractional/offset grammar is admitted at all."""
    schema = struct_of(_Meeting)
    decoded = schema.decode({"at": spelling})["at"]

    assert type(decoded) is time
    with pytest.raises(SchemaValueError) as error:
        schema.build({"at": decoded})
    assert str(error.value) == leaf


@pytest.mark.parametrize(
    "spelling",
    ["2020", "1430", "143000", "14:30:00.0000000", "14:30:00z", "24:00",
     "14:60", "14:30:60", "1:30", "14:30 ", " 14:30", "+14:30"],
)
def test_the_rejected_time_spellings_stay_text(spelling):
    assert struct_of(_Meeting).decode({"at": spelling})["at"] is spelling


@pytest.mark.parametrize(
    "spelling",
    ["20260808", "2026-W32-6", "2026-08-08T10:00", "2026/08/08", "2026-8-8",
     "2026-02-31", "0000-01-01", "2026-08-08 ", "＋2026-08-08", "２０２６-０８-０８"],
)
def test_the_rejected_date_spellings_stay_text(spelling):
    @dataclass
    class Booking:
        day: date

    assert struct_of(Booking).decode({"day": spelling})["day"] is spelling


# ==========================================================================
# 4. Invariants that survived the sweep — kept as fences
# ==========================================================================
def _containers(node, acc):
    """ids of every exact dict/list reachable in a tree."""
    if type(node) is dict:
        acc.add(id(node))
        for value in node.values():
            _containers(value, acc)
    elif type(node) is list:
        acc.add(id(node))
        for value in node:
            _containers(value, acc)
    return acc


def _spelling(node):
    """Type-sensitive shape of a tree: 3, 3.0 and True are three answers."""
    if type(node) is dict:
        return ("d", tuple(sorted((_spelling(k), _spelling(v))
                                  for k, v in node.items())))
    if type(node) is list:
        return ("l", tuple(_spelling(v) for v in node))
    return (type(node).__name__, repr(node))


@dataclass
class _Event:
    on: date
    at: time
    who: Role


@dataclass
class _Wide:
    event: _Event
    tags: list[str]
    when: str | date
    limit: int | float
    terms: list[str] | list[int]
    role: Role | Status
    maybe: date | None
    nested: list[list[date]]


_WIDE = struct_of(_Wide)

_HOSTILE = [
    {},
    {"when": {}},
    {"when": {"$type": "date"}},
    {"when": {"$value": "2026-08-08"}},
    {"when": {"$type": 7, "$value": "2026-08-08"}},
    {"when": {"$type": None, "$value": "2026-08-08"}},
    {"when": {"$type": ["date"], "$value": "2026-08-08"}},
    {"when": {"$type": "nope", "$value": "2026-08-08"}},
    {"when": {"$type": "date", "$value": "2026-08-08", "x": 1}},
    {"when": {"$type": "date", "$value": "nonsense"}},
    {"when": {"$type": "date", "$value": None}},
    {"when": {"$type": "date", "$value": ["2026-08-08"]}},
    {"when": {"$type": "date", "$value": {"$type": "date", "$value": "2026-08-08"}}},
    {"when": {"$type": "str", "$value": {"$type": "date", "$value": "2026-08-08"}}},
    {"limit": {"$type": "int", "$value": 3.5}},
    {"limit": {"$type": "float", "$value": "3"}},
    {"terms": {"$type": "list[str]", "$value": ["a"]}},
    {"terms": {"$type": "list[int]", "$value": [1]}},
    {"terms": {"$type": "list[int]", "$value": "nope"}},
    {"terms": ["a", 1, None]},
    {"role": {"$type": "Role", "$value": "ADMIN"}},
    {"role": {"$type": "Status", "$value": "ADMIN"}},
    {"role": "ADMIN"},
    {"event": None},
    {"event": []},
    {"event": {"on": {}, "at": [], "who": {"$type": "Role", "$value": "ADMIN"}}},
    {"event": {"$type": "_Event", "on": "2026-08-08"}},
    {"nested": [[["2026-08-08"]]]},
    {"nested": [[], [None], [{"$type": "date", "$value": "2026-08-08"}]]},
    {"maybe": None},
    {"unknown": {"$type": "date", "$value": "2026-08-08"}},
    {1: "x"},
    {"tags": {"$type": "list[str]", "$value": ["a"]}},
]


@pytest.mark.parametrize("data", _HOSTILE, ids=range(len(_HOSTILE)))
def test_decode_never_raises_never_mutates_and_never_shares_a_container(data):
    before = copy.deepcopy(data)

    out = _WIDE.decode(data)

    assert _spelling(data) == _spelling(before), "decode mutated its input"
    assert not _containers(data, set()) & _containers(out, set()), \
        "decode handed back a container from its input"
    assert set(out) == set(data), "decode invented or dropped a key"
    # docs/decode.md: decoding an already-exact tree is harmless.
    assert _spelling(_WIDE.decode(out)) == _spelling(out)


def test_a_root_that_is_not_a_dict_comes_back_as_it_came():
    instance = _Event(on=date(2026, 8, 8), at=time(14, 30), who=Role.ADMIN)
    for root in (None, "x", 3, 3.5, True, instance, (1, 2), frozenset({1})):
        assert _WIDE.decode(root) is root
    # A list root is rebuilt rather than shared, being a portable container.
    root_list = ["2026-08-08"]
    assert _WIDE.decode(root_list) == root_list
    assert _WIDE.decode(root_list) is not root_list


def test_aliasing_is_not_preserved_and_the_input_stays_whole():
    @dataclass
    class Pair:
        a: _Inner
        b: _Inner

    shared = {"when": "2026-08-08"}
    wire = {"a": shared, "b": shared}

    out = struct_of(Pair).decode(wire)

    assert out == {"a": {"when": date(2026, 8, 8)}, "b": {"when": date(2026, 8, 8)}}
    assert out["a"] is not out["b"]
    assert out["a"] is not shared and out["b"] is not shared
    assert wire == {"a": {"when": "2026-08-08"}, "b": {"when": "2026-08-08"}}


@pytest.mark.parametrize(
    "data, expected",
    [({"when": {"$type": "date", "$value": "2026-08-08"}}, date(2026, 8, 8)),
     ({"when": {"$type": "str", "$value": "2026-08-08"}}, "2026-08-08"),
     ({"limit": {"$type": "float", "$value": 3}}, 3.0),
     ({"limit": {"$type": "int", "$value": 3}}, 3),
     ({"role": {"$type": "Role", "$value": "ADMIN"}}, Role.ADMIN),
     ({"role": {"$type": "Status", "$value": "OPEN"}}, Status.OPEN)],
    ids=["date", "str", "float", "int", "Role", "Status"],
)
def test_a_consumed_portable_wrapper_lands_on_the_option_it_named(data, expected):
    key = next(iter(data))
    decoded = _WIDE.decode(data)[key]

    assert type(decoded) is type(expected)
    assert decoded == expected
    # And the option it named is the one `build` routes it to.
    built = _WIDE.build({**_COMPLETE, key: decoded})
    assert type(getattr(built, key)) is type(expected)


@pytest.mark.parametrize(
    "identity, payload",
    [("list[str]", ["a"]), ("list[int]", [1])],
)
def test_a_validation_wrapper_survives_decode_with_its_payload_decoded(identity, payload):
    data = {"terms": {"$type": identity, "$value": payload}}

    decoded = _WIDE.decode(data)["terms"]

    assert decoded == {"$type": identity, "$value": payload}
    assert decoded is not data["terms"]
    assert decoded["$value"] is not payload


_COMPLETE = {
    "event": {"on": date(2026, 8, 8), "at": time(14, 30), "who": Role.ADMIN},
    "tags": ["a"],
    "when": "text",
    "limit": 1,
    "terms": {"$type": "list[str]", "$value": ["a"]},
    "role": Role.USER,
    "maybe": None,
    "nested": [[date(2026, 8, 8)]],
}


def test_the_whole_wide_schema_round_trips_through_decode_then_build():
    wire = {
        "event": {"on": "2026-08-08", "at": "14:30", "who": "ADMIN"},
        "tags": ["a", "b"],
        "when": {"$type": "date", "$value": "2026-08-08"},
        "limit": {"$type": "float", "$value": 3},
        "terms": {"$type": "list[int]", "$value": [1, 2]},
        "role": {"$type": "Status", "$value": "SHUT"},
        "maybe": "2026-08-09",
        "nested": [["2026-08-08"], []],
    }
    frozen = copy.deepcopy(wire)

    built = _WIDE.build(_WIDE.decode(wire))

    assert wire == frozen
    assert built.event == _Event(on=date(2026, 8, 8), at=time(14, 30), who=Role.ADMIN)
    assert built.when == date(2026, 8, 8)
    assert built.limit == 3.0 and type(built.limit) is float
    assert built.terms == [1, 2]
    assert built.role is Status.SHUT
    assert built.maybe == date(2026, 8, 9)
    assert built.nested == [[date(2026, 8, 8)], []]


def test_decode_returns_the_enum_member_itself_including_through_an_alias():
    class Aliased(Enum):
        A = 1
        B = 1  # alias of A

    schema = _schema_for(Aliased)
    assert schema.decode({"x": "A"})["x"] is Aliased.A
    assert schema.decode({"x": "B"})["x"] is Aliased.A
    # By name, never by value, even when the two readings cross.
    class Cross(Enum):
        RED = "BLUE"
        BLUE = "RED"

    crossed = _schema_for(Cross)
    assert crossed.decode({"x": "RED"})["x"] is Cross.RED
    assert crossed.decode({"x": "BLUE"})["x"] is Cross.BLUE
    # A name that is not a member, and an attribute of the class, stay text.
    for probe in ("red", "nope", "name", "_member_map_", "__class__", "mro"):
        assert crossed.decode({"x": probe})["x"] is probe


def test_signature_decode_answers_the_same_way_as_struct_decode():
    def fn(when: date, note: str = "x"):
        ...

    sig = signature_of(fn)

    assert sig.decode({"when": "2026-08-08"}) == {"when": date(2026, 8, 8)}
    assert sig.decode({}) == {}
    assert sig.decode({"nope": "2026-08-08"}) == {"nope": "2026-08-08"}
    for root in (None, "x", 3, ("when",)):
        assert sig.decode(root) is root
    assert sig.decode({1: 1, "when": "2026-08-08"}) == {1: 1, "when": date(2026, 8, 8)}


# ==========================================================================
# 5. Generative sweep — the same oracles over portable trees
# ==========================================================================
_ATOMS = st.one_of(
    st.none(), st.booleans(), st.integers(min_value=-(2**70), max_value=2**70),
    st.floats(allow_nan=True, allow_infinity=True),
    st.sampled_from([
        "", "3", "3.5", "true", "null", "ADMIN", "OPEN", "nope",
        "2026-08-08", "2026-02-31", "20260808", "14:30", "14:30:00.5", "2020",
        "int", "float", "str", "date", "time", "None", "list[str]", "list[int]",
        "Role", "Status", "_Event", "$type", "$value",
    ]),
)


def _trees(depth):
    if depth == 0:
        return _ATOMS
    child = _trees(depth - 1)
    keys = st.sampled_from(["$type", "$value", "on", "at", "who", "when",
                            "limit", "terms", "role", "maybe", "nested",
                            "tags", "event", "x"])
    return st.one_of(
        _ATOMS,
        st.lists(child, max_size=3),
        st.dictionaries(keys, child, max_size=3),
    )


@settings(deadline=None, max_examples=400, derandomize=True)
@given(_trees(3))
def test_decode_is_total_and_leaves_the_portable_tree_it_was_given(tree):
    data = {"when": tree, "limit": tree, "terms": tree, "role": tree,
            "event": tree, "nested": tree, "tags": tree, "maybe": tree}
    before = copy.deepcopy(data)

    out = _WIDE.decode(data)

    assert _spelling(data) == _spelling(before)
    assert not _containers(data, set()) & _containers(out, set())
    assert set(out) == set(data)
    assert _spelling(_WIDE.decode(out)) == _spelling(out)


@settings(deadline=None, max_examples=400, derandomize=True)
@given(st.sampled_from(["date", "str", "float", "int", "Role", "Status",
                        "list[str]", "list[int]", "nope", "None", "time"]),
       _trees(2))
def test_a_wrapper_is_either_consumed_onto_its_option_or_handed_back(identity, payload):
    wrapper = {"$type": identity, "$value": payload}
    for key in ("when", "limit", "terms", "role"):
        decoded = _WIDE.decode({key: wrapper})[key]
        if type(decoded) is dict and set(decoded) == {"$type", "$value"}:
            # Handed back, or kept as a validation wrapper: the identity is
            # never rewritten and the payload is never dropped.
            assert decoded["$type"] == identity
            continue
        # Consumed: `build` must route it to the option the caller named, so a
        # type error here would mean the value landed somewhere else.
        try:
            _WIDE.build({**_COMPLETE, key: decoded})
        except SchemaTypeError as error:  # pragma: no cover - fails the test
            pytest.fail(f"{wrapper!r} on {key!r} decoded to {decoded!r}: {error}")
        except SchemaValueError:
            pass  # the named shape reporting its own rule is documented

"""Where `decode` sends a portable value, and where it refuses to send it.

`Struct.decode` / `Signature.decode` restore the four shapes the transport
spells as something else, and nothing more. This file pins the *routing* half of
docs/decode.md: which option of a union a bare value reaches, what happens to the
`$type`/`$value` wrapper of docs/build.md once decoding is done with it, and how
lists and dataclasses are descended.

The governing sentence is docs/decode.md, "Unions":

    The schema decides the reading. Where more than one option could read a
    portable value, the caller names the option, or the value stands as it came.

Every routing test comes in two halves, because the two operations only make
sense together: what `decode` returns, and what `build` then does with it. A
value decode leaves alone is not a value that vanished — it is a value handed to
validation with its own coordinates, exactly as it arrived.

Scalar decoding on its own (canonical spellings, enum member names, the
non-coercion battery) lives in the scalar decode tests; this file only uses
those spellings as the raw material for routing decisions.
"""

from dataclasses import dataclass, field, make_dataclass
from datetime import date, time
from enum import Enum
from typing import Annotated

import pytest

from pytypehint import (
    Min, SchemaTypeError, SchemaValueError, signature_of, struct_of,
)


class _Role(Enum):
    ADMIN = "admin"
    GUEST = "guest"


class _Status(Enum):
    ACTIVE = "active"
    CLOSED = "closed"


@dataclass
class _Shirt:
    size: str
    when: date | None = None


@dataclass
class _Mug:
    capacity: int


@dataclass
class _Address:
    city: str
    since: date


@dataclass
class _Person:
    name: str
    address: _Address


@dataclass
class _Node:
    when: date | None = None
    children: "list[_Node]" = field(default_factory=list)


@dataclass
class _Beta:
    at: time | None = None
    alpha: "_Alpha | None" = None


@dataclass
class _Alpha:
    on: date | None = None
    beta: "_Beta | None" = None


def _compile(hint):
    return struct_of(make_dataclass("C", [("v", hint)]))


def _wrap(option, value):
    return {"$type": option, "$value": value}


def _decode_v(hint, value):
    return _compile(hint).decode({"v": value})["v"]


# ------------------------------------------------------------------------
# 1. A portable spelling two options share: the value stands as it came
# ------------------------------------------------------------------------

_COLLIDING = [
    (int | float, 3),
    (int | float, 0),
    (int | float, -7),
    (str | date, "2026-08-08"),
    (str | date, "hello"),
    (str | time, "14:30"),
    (str | time, "14:30:00"),
    (date | time, "2026-08-08"),
    (date | time, "14:30"),
    (date | time, "nonsense"),
    (_Role | _Status, "ADMIN"),
    (_Role | _Status, "ACTIVE"),
    (_Role | _Status, "NOBODY"),
    (_Role | str, "ADMIN"),
    (_Role | str, "not a member"),
]


@pytest.mark.parametrize("hint, wire", _COLLIDING)
def test_a_bare_value_two_options_could_read_is_returned_exactly_as_it_came(hint, wire):
    """docs/decode.md: "Where the spellings collide, nothing is decoded"."""
    decoded = _decode_v(hint, wire)

    assert decoded == wire
    assert type(decoded) is type(wire)


@pytest.mark.parametrize("hint, wire, expected_type", [
    (int | float, 3, int),
    (int | float, 0, int),
    (str | date, "2026-08-08", str),
    (str | date, "hello", str),
    (str | time, "14:30", str),
    (_Role | str, "ADMIN", str),
])
def test_build_routes_the_undecoded_value_to_the_option_that_takes_it_unchanged(
        hint, wire, expected_type):
    """docs/decode.md, the collision table: "unchanged; `build` routes it to `int`" / to `str`."""
    schema = _compile(hint)

    built = schema.build(schema.decode({"v": wire}))

    assert built.v == wire
    assert type(built.v) is expected_type


@pytest.mark.parametrize("hint, wire, message", [
    (date | time, "2026-08-08", "v: expected date | time, got str"),
    (date | time, "14:30", "v: expected date | time, got str"),
    (date | time, "nonsense", "v: expected date | time, got str"),
    (_Role | _Status, "ADMIN", "v: expected _Role | _Status, got str"),
    (_Role | _Status, "ACTIVE", "v: expected _Role | _Status, got str"),
])
def test_build_reports_the_undecoded_value_where_no_option_accepts_the_raw_spelling(
        hint, wire, message):
    """docs/decode.md, the collision table: "unchanged; `build` reports `expected date | time, got str`"."""
    schema = _compile(hint)

    with pytest.raises(SchemaTypeError) as error:
        schema.build(schema.decode({"v": wire}))

    assert str(error.value) == message


def test_a_colliding_union_leaves_the_value_alone_at_every_depth():
    """The collision is a property of the options, not of where they sit."""
    schema = _compile(list[date | time])

    assert schema.decode({"v": ["2026-08-08", "14:30"]}) == {"v": ["2026-08-08", "14:30"]}


# ------------------------------------------------------------------------
# 2. Exactly one option can be spelled that way: decode converts
# ------------------------------------------------------------------------

@pytest.mark.parametrize("hint, wire, expected", [
    (int | str, 3, 3),
    (int | str, "3", "3"),
    (bool | str, True, True),
    (bool | str, "true", "true"),
    (float | str, 3, 3.0),
    (date | None, "2026-08-08", date(2026, 8, 8)),
    (date | None, None, None),
    (date | None, "hello", "hello"),
    (time | None, "14:30", time(14, 30)),
    (_Role | None, "ADMIN", _Role.ADMIN),
    (_Role | int, "ADMIN", _Role.ADMIN),
    (list[date] | str, ["2026-08-08"], [date(2026, 8, 8)]),
    (list[date] | str, "2026-08-08", "2026-08-08"),
])
def test_one_candidate_decodes_even_though_the_field_is_a_union(hint, wire, expected):
    """docs/decode.md: "A value is decoded into an option when exactly one option can be spelled that way"."""
    decoded = _decode_v(hint, wire)

    assert decoded == expected
    assert type(decoded) is type(expected)


def test_a_dataclass_beside_a_scalar_is_still_descended():
    """A dict reaches only the dataclass option, so the reading is not in doubt."""
    assert _decode_v(_Shirt | str, {"size": "M", "when": "2026-08-08"}) == {
        "size": "M", "when": date(2026, 8, 8)}
    assert _decode_v(_Shirt | str, "M") == "M"


def test_a_dataclass_beside_a_list_is_still_descended_and_so_is_the_list():
    """`dict` and `list` are different portable spellings; each option owns one."""
    assert _decode_v(_Shirt | list[date], {"size": "M", "when": "2026-08-08"}) == {
        "size": "M", "when": date(2026, 8, 8)}
    assert _decode_v(_Shirt | list[date], ["2026-08-08"]) == [date(2026, 8, 8)]


def test_a_decoded_single_candidate_union_builds_without_a_discriminator():
    """docs/build.md: "`int | str`, `list[str | int]` and `list[int] | None` route themselves by exact type"."""
    schema = _compile(date | None)

    assert schema.build(schema.decode({"v": "2026-08-08"})).v == date(2026, 8, 8)
    assert schema.build(schema.decode({"v": None})).v is None


# ------------------------------------------------------------------------
# 3. The wrapper is CONSUMED where the options differ in Python
# ------------------------------------------------------------------------

_CONSUMED = [
    (str | date, "date", "2026-08-08", date(2026, 8, 8)),
    (str | date, "str", "2026-08-08", "2026-08-08"),
    (str | time, "time", "14:30:00", time(14, 30)),
    (str | time, "str", "14:30", "14:30"),
    (int | float, "float", 3, 3.0),
    (int | float, "int", 3, 3),
    (int | float, "float", 3.5, 3.5),
    (date | time, "time", "14:30:00", time(14, 30)),
    (date | time, "date", "2026-08-08", date(2026, 8, 8)),
    (_Role | _Status, "_Status", "ACTIVE", _Status.ACTIVE),
    (_Role | _Status, "_Role", "ADMIN", _Role.ADMIN),
    (_Role | str, "_Role", "ADMIN", _Role.ADMIN),
    (_Role | str, "str", "ADMIN", "ADMIN"),
]


@pytest.mark.parametrize("hint, option, payload, expected", _CONSUMED)
def test_a_wrapper_naming_options_that_share_only_a_spelling_is_consumed(
        hint, option, payload, expected):
    """docs/decode.md: options that "share only a **portable** spelling ... are distinct Python values once decoded, so the wrapper has done its work and is consumed"."""
    decoded = _decode_v(hint, _wrap(option, payload))

    assert decoded == expected
    assert type(decoded) is type(expected)


@pytest.mark.parametrize("hint, option, payload, expected", _CONSUMED)
def test_build_accepts_the_bare_value_the_consumed_wrapper_left_behind(
        hint, option, payload, expected):
    """The wrapper is not data: once decode has used it, `build` sees an ordinary value."""
    schema = _compile(hint)

    built = schema.build(schema.decode({"v": _wrap(option, payload)}))

    assert built.v == expected
    assert type(built.v) is type(expected)


def test_a_consumed_wrapper_returns_the_enum_member_itself():
    """docs/decode.md: "Decode returns the member itself, not a copy, so `is` comparisons hold"."""
    assert _decode_v(_Role | _Status, _wrap("_Role", "GUEST")) is _Role.GUEST


@pytest.mark.parametrize("payload, expected, message", [
    ("10:00:00.5", time(10, 0, 0, 500000),
     "v: time precision is limited to whole seconds: 10:00:00.500000"),
])
def test_a_consumed_wrapper_still_hands_a_refused_spelling_to_validation(
        payload, expected, message):
    """docs/decode.md: "A spelling the schema will refuse is still read, so the shape reports its own rule"."""
    schema = _compile(date | time)

    decoded = schema.decode({"v": _wrap("time", payload)})
    assert decoded == {"v": expected}

    with pytest.raises(SchemaValueError) as error:
        schema.build(decoded)
    assert str(error.value) == message


# ------------------------------------------------------------------------
# 4. The wrapper is PRESERVED where the options share a Python type
# ------------------------------------------------------------------------

_PRESERVED = [
    (list[str] | list[int], "list[str]", ["a"], ["a"]),
    (list[str] | list[int], "list[int]", [1, 2], [1, 2]),
    (list[str] | list[int], "list[int]", [], []),
    (Annotated[list[str], Min(1)] | list[int], "list[str]", ["a"], ["a"]),
    (Annotated[list[str], Min(1)] | list[int], "list[int]", [], []),
    (list[list[str]] | list[list[int]], "list[list[int]]", [[1], [2, 3]], [[1], [2, 3]]),
    (list[list[str]] | list[list[int]], "list[list[str]]", [["a"]], [["a"]]),
    (list[date] | list[str], "list[date]", ["2026-08-08"], [date(2026, 8, 8)]),
    (list[date] | list[str], "list[str]", ["2026-08-08"], ["2026-08-08"]),
    (list[date] | list[str], "list[date]", [], []),
]


@pytest.mark.parametrize("hint, option, payload, expected", _PRESERVED)
def test_a_wrapper_naming_options_that_share_a_python_type_is_kept(
        hint, option, payload, expected):
    """docs/decode.md: options that "also share a **Python** runtime type ... cannot be told apart after decoding either, so the wrapper is kept and only its payload is decoded"."""
    decoded = _decode_v(hint, _wrap(option, payload))

    assert decoded == _wrap(option, expected)


@pytest.mark.parametrize("hint, option, payload, expected", _PRESERVED)
def test_build_unwraps_the_wrapper_decode_kept(hint, option, payload, expected):
    """docs/build.md: "struct_of(Query).build(data) # Query(terms=['a', 'b']); consumes the wrapper"."""
    schema = _compile(hint)

    assert schema.build(schema.decode({"v": _wrap(option, payload)})).v == expected


def test_the_payload_of_a_preserved_wrapper_is_decoded_inside_it():
    """docs/decode.md: "the wrapper is kept and only its payload is decoded" — the payload really is decoded."""
    decoded = _decode_v(list[date] | list[str], _wrap("list[date]", ["2026-08-08", "2020-01-01"]))

    assert decoded == _wrap("list[date]", [date(2026, 8, 8), date(2020, 1, 1)])
    assert set(decoded) == {"$type", "$value"}
    assert [type(item) for item in decoded["$value"]] == [date, date]


def test_a_preserved_wrapper_decodes_dataclass_payloads_below_it():
    """The wrapper selects the list; decoding then descends into each item's fields."""
    decoded = _decode_v(list[_Shirt] | list[_Mug],
                        _wrap("list[_Shirt]", [{"size": "M", "when": "2026-08-08"}]))

    assert decoded == _wrap("list[_Shirt]", [{"size": "M", "when": date(2026, 8, 8)}])


def test_a_preserved_wrapper_decodes_nested_list_payloads_below_it():
    decoded = _decode_v(list[list[date]] | list[list[str]],
                        _wrap("list[list[date]]", [["2026-08-08"], []]))

    assert decoded == _wrap("list[list[date]]", [[date(2026, 8, 8)], []])


def test_an_annotated_option_keeps_the_plain_identity_in_the_preserved_wrapper():
    """docs/restrictions.md, 'Option identity': "atoms narrow a type, they do not create one"."""
    decoded = _decode_v(Annotated[list[str], Min(1)] | list[int], _wrap("list[str]", ["a"]))

    assert decoded == _wrap("list[str]", ["a"])


def test_a_preserved_wrapper_is_a_fresh_dict_and_never_the_input_one():
    """docs/decode.md: "`decode` never modifies the tree it is given, and never hands back a container from it"."""
    schema = _compile(list[date] | list[str])
    wire = {"v": _wrap("list[date]", ["2026-08-08"])}

    decoded = schema.decode(wire)

    assert decoded["v"] is not wire["v"]
    assert decoded["v"]["$value"] is not wire["v"]["$value"]
    assert wire == {"v": _wrap("list[date]", ["2026-08-08"])}


# ------------------------------------------------------------------------
# 5. A bare list under two list options is never descended into
# ------------------------------------------------------------------------

_AMBIGUOUS_LISTS = [[], ["a"], [1], [1, "a"], ["a", "b", "c"], [None]]


@pytest.mark.parametrize("wire", _AMBIGUOUS_LISTS)
def test_a_bare_list_under_two_list_options_is_handed_back_undescended(wire):
    """docs/decode.md, the collision table: "`list[str] | list[int]` | an array | unchanged"."""
    decoded = _decode_v(Annotated[list[str], Min(1)] | list[int], wire)

    assert decoded == wire
    assert [type(item) for item in decoded] == [type(item) for item in wire]


@pytest.mark.parametrize("wire", _AMBIGUOUS_LISTS)
def test_build_reports_a_bare_ambiguous_list_and_names_the_way_out(wire):
    """docs/build.md: "ambiguous list: field accepts list[str] | list[int] — wrap it as ... naming the option"."""
    schema = _compile(Annotated[list[str], Min(1)] | list[int])

    with pytest.raises(SchemaTypeError,
                       match=r"ambiguous list: field accepts list\[str\] \| list\[int\]"):
        schema.build(schema.decode({"v": wire}))


def test_a_min_atom_on_one_option_does_not_select_a_branch():
    """docs/restrictions.md: "atoms narrow a type, they do not create one" — Min(1) is not evidence about which list this is.

    `["a"]` satisfies Min(1) and `list[str]`; `[]` violates Min(1) and would
    therefore "have to" be the `list[int]` arm. Neither reading is decode's to
    make, so both are handed back exactly as they came.
    """
    schema = _compile(Annotated[list[str], Min(1)] | list[int])

    assert schema.decode({"v": []}) == {"v": []}
    assert schema.decode({"v": ["a"]}) == {"v": ["a"]}


def test_an_empty_list_falls_to_no_branch_at_all():
    """docs/restrictions.md: "Given `[]`, `list[int] | list[str]` has no answer in the data"."""
    assert _decode_v(list[date] | list[str], []) == []
    assert _decode_v(list[str] | list[int], []) == []


def test_a_bare_ambiguous_list_is_not_descended_even_when_one_branch_would_decode():
    """The contents never select the option, so `"2026-08-08"` is not read as a date here."""
    decoded = _decode_v(list[date] | list[str], ["2026-08-08"])

    assert decoded == ["2026-08-08"]
    assert type(decoded[0]) is str


def test_an_undescended_ambiguous_list_is_still_a_fresh_list():
    """docs/decode.md: "A subtree decode cannot route is copied rather than shared"."""
    schema = _compile(list[str] | list[int])
    payload = ["a"]

    decoded = schema.decode({"v": payload})

    assert decoded["v"] == payload
    assert decoded["v"] is not payload


# ------------------------------------------------------------------------
# 6. A wrapper whose payload did not reach its option is left alone
# ------------------------------------------------------------------------

_UNREACHED = [
    (str | date, "date", "nonsense", "v: expected str | date, got dict"),
    (str | date, "date", "2026-02-31", "v: expected str | date, got dict"),
    (str | date, "date", "20260808", "v: expected str | date, got dict"),
    (str | date, "date", 5, "v: expected str | date, got dict"),
    (int | float, "float", "x", "v: expected int | float, got dict"),
    (int | float, "int", 3.0, "v: expected int | float, got dict"),
    (date | time, "time", "nope", "v: expected date | time, got dict"),
    (date | time, "date", "14:30", "v: expected date | time, got dict"),
    (_Role | str, "_Role", "NOPE", "v: expected _Role | str, got dict"),
    (_Role | _Status, "_Status", "ADMIN", "v: expected _Role | _Status, got dict"),
    (list[str] | list[int], "list[str]", 5, "v: $value: expected list, got int"),
]


@pytest.mark.parametrize("hint, option, payload, message", _UNREACHED)
def test_a_wrapper_whose_payload_missed_its_option_survives_untouched(
        hint, option, payload, message):
    """docs/decode.md: "A wrapper whose payload did not reach the option it named is also left alone"."""
    schema = _compile(hint)
    wire = {"v": _wrap(option, payload)}

    decoded = schema.decode(wire)

    assert decoded == wire
    assert type(decoded["v"]) is dict
    assert decoded["v"] is not wire["v"]


@pytest.mark.parametrize("hint, option, payload, message", _UNREACHED)
def test_build_reports_the_wrapper_the_failed_payload_left_standing(
        hint, option, payload, message):
    """docs/decode.md: "build ──▶ when: expected str | date, got dict"."""
    schema = _compile(hint)

    with pytest.raises(SchemaTypeError) as error:
        schema.build(schema.decode({"v": _wrap(option, payload)}))

    assert str(error.value) == message


def test_a_date_that_failed_to_parse_is_not_filed_as_the_str_beside_it():
    """docs/decode.md: "Consuming it would file the value under a different option in silence — a date that failed to parse would settle as the `str` beside it".

    This is the whole reason the wrapper is checked against its payload rather
    than trusted: `str | date` would accept `"nonsense"` happily as a `str`, and
    the caller who wrote `$type: "date"` would never learn the date was broken.
    """
    schema = _compile(str | date)

    decoded = schema.decode({"v": _wrap("date", "nonsense")})

    assert decoded == {"v": _wrap("date", "nonsense")}
    with pytest.raises(SchemaTypeError) as error:
        schema.build(decoded)
    assert str(error.value) == "v: expected str | date, got dict"


def test_a_calendar_impossible_date_keeps_its_wrapper_too():
    """docs/decode.md: "A canonical spelling that names no real day — `"2026-02-31"` — is left as `str`" — so the wrapper naming `date` is not consumed either."""
    assert _decode_v(str | date, _wrap("date", "2026-02-31")) == _wrap("date", "2026-02-31")


def test_a_preserved_wrapper_keeps_a_payload_of_the_wrong_type_for_its_own_diagnosis():
    """docs/build.md: "Failures keep their coordinates, including `$value`" — decode does not pre-empt them."""
    schema = _compile(list[str] | list[int])

    decoded = schema.decode({"v": _wrap("list[str]", 5)})
    assert decoded == {"v": _wrap("list[str]", 5)}

    with pytest.raises(SchemaTypeError) as error:
        schema.build(decoded)
    assert error.value.path == ("v", "$value")
    assert str(error.value) == "v: $value: expected list, got int"


# ------------------------------------------------------------------------
# 7. Malformed wrappers are handed back untouched
# ------------------------------------------------------------------------

_MALFORMED_LIST_WRAPPERS = [
    ({},
     "v: ambiguous value: field accepts list[str] | list[int]"),
    ({"$type": "list[str]"},
     "v: missing key(s): $value"),
    ({"$value": ["a"]},
     "v: ambiguous value: field accepts list[str] | list[int]"),
    ({"$type": "list[str]", "$value": ["a"], "note": 1},
     "v: unexpected key(s): note"),
    ({"$type": "list[str]", "$value": ["a"], "note": 1, "also": 2},
     "v: unexpected key(s): also, note"),
    ({"$type": None, "$value": ["a"]},
     "v: $type: expected str, got NoneType"),
    ({"$type": 1, "$value": ["a"]},
     "v: $type: expected str, got int"),
    ({"$type": ["list[str]"], "$value": ["a"]},
     "v: $type: expected str, got list"),
    ({"$type": "list[float]", "$value": ["a"]},
     "v: $type: not a choice: 'list[float]', expected one of ('list[str]', 'list[int]')"),
    ({"$type": "list[str]", "$value": {"$type": "list[str]", "$value": ["a"]}},
     "v: $value: expected list, got dict"),
    ({"$type": "list[str]", "$value": 5},
     "v: $value: expected list, got int"),
]


@pytest.mark.parametrize("wrapper, message", _MALFORMED_LIST_WRAPPERS)
def test_a_malformed_wrapper_is_handed_back_exactly_as_it_arrived(wrapper, message):
    """docs/decode.md: "Malformed wrappers ... are all handed back untouched"."""
    schema = _compile(list[str] | list[int])
    wire = {"v": wrapper}

    decoded = schema.decode(wire)

    assert decoded == wire
    assert decoded["v"] is not wire["v"]


@pytest.mark.parametrize("wrapper, message", _MALFORMED_LIST_WRAPPERS)
def test_build_reports_each_malformed_wrapper_with_the_wording_it_already_had(
        wrapper, message):
    """docs/decode.md: "`build` reports each with the message and the coordinates it already had. Decode never reproduces that diagnosis"."""
    schema = _compile(list[str] | list[int])

    with pytest.raises((SchemaTypeError, SchemaValueError)) as error:
        schema.build(schema.decode({"v": wrapper}))

    assert str(error.value).startswith(message)


@pytest.mark.parametrize("wrapper", [
    {},
    {"$type": "date"},
    {"$value": "2026-08-08"},
    {"$type": "date", "$value": "2026-08-08", "note": 1},
    {"$type": None, "$value": "2026-08-08"},
    {"$type": 1, "$value": "2026-08-08"},
    {"$type": "nope", "$value": "2026-08-08"},
    {"$type": "date", "$value": {"$type": "date", "$value": "2026-08-08"}},
    {"$type": "date", "$value": 5},
    {"$type": "date", "$value": None},
])
def test_a_malformed_wrapper_on_a_consuming_union_is_left_for_build_to_report(wrapper):
    """docs/decode.md: a malformed wrapper is "an ordinary foreign dictionary" — here the options never share a Python type, so `build` reports the dict itself."""
    schema = _compile(str | date)

    decoded = schema.decode({"v": wrapper})
    assert decoded == {"v": wrapper}

    with pytest.raises(SchemaTypeError) as error:
        schema.build(decoded)
    assert str(error.value) == "v: expected str | date, got dict"


def test_a_wrapper_nested_inside_a_wrapper_is_not_unpeeled():
    """docs/decode.md lists "a wrapper nested in a wrapper" among the malformed shapes."""
    inner = _wrap("date", "2026-08-08")

    assert _decode_v(str | date, _wrap("date", inner)) == _wrap("date", inner)


def test_an_extra_key_disqualifies_the_whole_wrapper_including_its_payload():
    """docs/build.md: "The wrapper carries those two keys and nothing else" — so its payload is not decoded either."""
    wrapper = {"$type": "date", "$value": "2026-08-08", "note": 1}

    decoded = _decode_v(str | date, wrapper)

    assert decoded == wrapper
    assert type(decoded["$value"]) is str


def test_an_unknown_option_identity_leaves_the_payload_unread():
    """docs/decode.md: "an unknown identity" is malformed, and a malformed wrapper is not a route."""
    wrapper = {"$type": "datetime", "$value": "2026-08-08"}

    decoded = _decode_v(str | date, wrapper)

    assert decoded == wrapper
    assert type(decoded["$value"]) is str


# ------------------------------------------------------------------------
# 8. A wrapper where nothing is ambiguous is an ordinary foreign dict
# ------------------------------------------------------------------------

@pytest.mark.parametrize("hint, wrapper, message", [
    (str, _wrap("str", "a"), "v: expected str, got dict"),
    (list[str], _wrap("list[str]", ["a"]), "v: expected list, got dict"),
    (date, _wrap("date", "2026-08-08"), "v: expected date, got dict"),
    (_Role, _wrap("_Role", "ADMIN"), "v: expected _Role, got dict"),
    (int | str, _wrap("int", 1), "v: expected int | str, got dict"),
    (date | None, _wrap("date", "2026-08-08"), "v: expected date | NoneType, got dict"),
    (list[int] | None, _wrap("list[int]", [1]), "v: expected list | NoneType, got dict"),
    (list[str | int], _wrap("list[str]", ["a"]), "v: expected list, got dict"),
])
def test_a_wrapper_on_an_unambiguous_field_is_neither_consumed_nor_descended(
        hint, wrapper, message):
    """docs/decode.md: "A wrapper is accepted only where the reading is genuinely ambiguous ... On a single-option field it is an ordinary foreign dictionary and is left alone, so `build` reports it"."""
    schema = _compile(hint)

    decoded = schema.decode({"v": wrapper})
    assert decoded == {"v": wrapper}

    with pytest.raises(SchemaTypeError) as error:
        schema.build(decoded)
    assert str(error.value) == message


def test_a_wrapper_on_a_single_option_field_does_not_decode_its_payload():
    """The payload is not read at all: the dict is foreign from the first key on."""
    decoded = _decode_v(date, _wrap("date", "2026-08-08"))

    assert type(decoded["$value"]) is str


# ------------------------------------------------------------------------
# 9. Lists
# ------------------------------------------------------------------------

@pytest.mark.parametrize("wire, expected", [
    ([], []),
    (["2026-08-08"], [date(2026, 8, 8)]),
    (["2026-08-08", "2020-01-01", "1999-12-31"],
     [date(2026, 8, 8), date(2020, 1, 1), date(1999, 12, 31)]),
    (["2026-08-08", "hello"], [date(2026, 8, 8), "hello"]),
    (["hello"], ["hello"]),
])
def test_a_list_decodes_each_item_and_keeps_the_ones_it_cannot(wire, expected):
    """docs/decode.md: "a value decode cannot restore is handed back exactly as it came"."""
    assert _decode_v(list[date], wire) == expected


def test_an_item_decode_could_not_restore_reports_with_its_own_index():
    schema = _compile(list[date])

    with pytest.raises(SchemaTypeError) as error:
        schema.build(schema.decode({"v": ["2026-08-08", "hello"]}))

    assert error.value.path == ("v", 1)
    assert str(error.value) == "v: [1]: expected date, got str"


@pytest.mark.parametrize("wire, expected", [
    ([], []),
    ([[]], [[]]),
    ([["2026-08-08"], []], [[date(2026, 8, 8)], []]),
    ([["2026-08-08"], ["2020-01-01", "nope"]],
     [[date(2026, 8, 8)], [date(2020, 1, 1), "nope"]]),
])
def test_nested_lists_are_descended_to_the_bottom(wire, expected):
    assert _decode_v(list[list[date]], wire) == expected


def test_a_list_of_dataclasses_descends_into_every_element():
    decoded = _decode_v(list[_Address], [{"city": "Madrid", "since": "2026-08-08"},
                                         {"city": "Vigo", "since": "nope"}])

    assert decoded == [{"city": "Madrid", "since": date(2026, 8, 8)},
                       {"city": "Vigo", "since": "nope"}]


@pytest.mark.parametrize("hint, wire, expected", [
    (list[int | _Role], [1, "ADMIN"], [1, _Role.ADMIN]),
    (list[int | _Role], ["NOPE"], ["NOPE"]),
    (list[date | None], ["2026-08-08", None], [date(2026, 8, 8), None]),
    (list[date | None], [None, "hello"], [None, "hello"]),
    (list[str | date], ["2026-08-08"], ["2026-08-08"]),
])
def test_a_list_of_a_union_routes_each_item_on_its_own(hint, wire, expected):
    """docs/build.md: "`list[str | int]` ... route themselves by exact type" — item by item."""
    decoded = _decode_v(hint, wire)

    assert decoded == expected
    assert [type(item) for item in decoded] == [type(item) for item in expected]


def test_a_list_item_may_carry_its_own_inline_discriminator():
    """docs/decode.md: "Where a union holds two or more dataclasses, it descends through the inline `$type` that `build` already reads, and keeps it"."""
    schema = _compile(list[_Shirt | _Mug])
    wire = {"v": [{"$type": "_Shirt", "size": "M", "when": "2026-08-08"},
                  {"$type": "_Mug", "capacity": 3}]}

    decoded = schema.decode(wire)

    assert decoded == {"v": [{"$type": "_Shirt", "size": "M", "when": date(2026, 8, 8)},
                             {"$type": "_Mug", "capacity": 3}]}
    assert schema.build(decoded).v == [_Shirt("M", date(2026, 8, 8)), _Mug(3)]


def test_a_list_item_may_carry_its_own_value_wrapper():
    """The wrapper is a value-level device, so it works wherever the item's own union is ambiguous."""
    schema = _compile(list[str | date])
    wire = {"v": [_wrap("date", "2026-08-08"), "plain"]}

    decoded = schema.decode(wire)

    assert decoded == {"v": [date(2026, 8, 8), "plain"]}
    assert schema.build(decoded).v == [date(2026, 8, 8), "plain"]


def test_a_list_of_ambiguous_lists_keeps_a_wrapper_per_element():
    schema = _compile(list[list[str] | list[int]])
    wire = {"v": [_wrap("list[int]", [1]), _wrap("list[str]", ["a"])]}

    decoded = schema.decode(wire)

    assert decoded == wire
    assert schema.build(decoded).v == [[1], ["a"]]


def test_every_list_in_the_result_is_freshly_built():
    """docs/decode.md: "Every dict and list in the result is newly built"."""
    schema = _compile(list[list[date]])
    wire = {"v": [["2026-08-08"]]}

    decoded = schema.decode(wire)

    assert decoded["v"] is not wire["v"]
    assert decoded["v"][0] is not wire["v"][0]


def test_aliasing_in_the_input_is_not_preserved():
    """docs/decode.md: "one dict referenced twice in the input becomes two independent dicts in the output"."""
    shared = ["2026-08-08"]

    decoded = _decode_v(list[list[date]], [shared, shared])

    assert decoded == [[date(2026, 8, 8)], [date(2026, 8, 8)]]
    assert decoded[0] is not decoded[1]


# ------------------------------------------------------------------------
# 10. Dataclasses
# ------------------------------------------------------------------------

def test_a_flat_dataclass_is_descended_by_field_name():
    """docs/decode.md: "A dataclass arrives as a dict and decode descends into it by field name"."""
    assert struct_of(_Address).decode({"city": "Madrid", "since": "2026-08-08"}) == {
        "city": "Madrid", "since": date(2026, 8, 8)}


def test_a_nested_dataclass_is_descended_at_its_own_depth():
    schema = struct_of(_Person)
    wire = {"name": "Ana", "address": {"city": "Madrid", "since": "2026-08-08"}}

    decoded = schema.decode(wire)

    assert decoded == {"name": "Ana",
                       "address": {"city": "Madrid", "since": date(2026, 8, 8)}}
    assert schema.build(decoded) == _Person("Ana", _Address("Madrid", date(2026, 8, 8)))


def test_a_recursive_dataclass_is_descended_to_the_bottom():
    schema = struct_of(_Node)
    wire = {"when": "2026-08-08",
            "children": [{"when": "2020-01-01",
                          "children": [{"when": "1999-12-31", "children": []}]}]}

    decoded = schema.decode(wire)

    assert decoded == {"when": date(2026, 8, 8),
                       "children": [{"when": date(2020, 1, 1),
                                     "children": [{"when": date(1999, 12, 31),
                                                   "children": []}]}]}
    assert schema.build(decoded).children[0].children[0].when == date(1999, 12, 31)


def test_a_dataclass_union_keeps_its_inline_discriminator_and_descends_through_it():
    """docs/decode.md: "struct_of(Order).decode(...) # {'event': {'$type': 'Shipped', 'on': datetime.date(2026, 8, 8)}}"."""
    schema = _compile(_Shirt | _Mug)
    wire = {"v": {"$type": "_Shirt", "size": "M", "when": "2026-08-08"}}

    decoded = schema.decode(wire)

    assert decoded == {"v": {"$type": "_Shirt", "size": "M", "when": date(2026, 8, 8)}}
    assert schema.build(decoded).v == _Shirt("M", date(2026, 8, 8))


@pytest.mark.parametrize("wire, message", [
    ({"$type": "_Other", "size": "M", "when": "2026-08-08"},
     "v: $type: not a choice: '_Other', expected one of ('_Shirt', '_Mug')"),
    ({"size": "M", "when": "2026-08-08"},
     'v: ambiguous dict: field accepts _Shirt | _Mug — add "$type" naming the variant'),
    ({"$type": 1, "size": "M", "when": "2026-08-08"},
     "v: $type: expected str, got int"),
    ({"$type": None, "size": "M", "when": "2026-08-08"},
     "v: $type: expected str, got NoneType"),
])
def test_an_unknown_or_missing_discriminator_leaves_the_dict_undecoded(wire, message):
    """docs/decode.md: "An unknown or missing discriminator leaves the dict undecoded, for `build` to report"."""
    schema = _compile(_Shirt | _Mug)

    decoded = schema.decode({"v": wire})
    assert decoded == {"v": wire}
    assert type(decoded["v"]["when"]) is str

    with pytest.raises((SchemaTypeError, SchemaValueError)) as error:
        schema.build(decoded)
    assert str(error.value) == message


def test_a_dataclass_item_without_a_discriminator_is_left_undecoded_inside_a_list():
    schema = _compile(list[_Shirt | _Mug])

    decoded = schema.decode({"v": [{"size": "M", "when": "2026-08-08"}]})

    assert decoded == {"v": [{"size": "M", "when": "2026-08-08"}]}
    with pytest.raises(SchemaTypeError,
                       match=r"v: \[0\]: ambiguous dict: field accepts _Shirt \| _Mug"):
        schema.build(decoded)


@pytest.mark.parametrize("wire", [None, [], ["a"], "not a dict", 5, 3.0, True])
def test_a_root_that_is_not_a_dict_is_returned_as_it_came(wire):
    """docs/decode.md: "A root that is not a dict ... is returned as it came, and `build` reports it"."""
    schema = struct_of(_Address)

    assert schema.decode(wire) == wire
    with pytest.raises(SchemaTypeError):
        schema.build(schema.decode(wire))


@pytest.mark.parametrize("wire", [None, [], "not a dict", 5])
def test_a_dataclass_field_that_is_not_a_dict_is_returned_as_it_came(wire):
    schema = _compile(_Address)

    assert schema.decode({"v": wire}) == {"v": wire}


def test_unknown_keys_travel_through_untouched_and_are_never_decoded():
    """docs/decode.md: "Unknown keys travel through untouched, so `resolve` still reports them as unexpected"."""
    decoded = struct_of(_Address).decode(
        {"city": "Madrid", "since": "2026-08-08", "nope": "2026-08-08"})

    assert decoded == {"city": "Madrid", "since": date(2026, 8, 8), "nope": "2026-08-08"}
    assert type(decoded["nope"]) is str


def test_an_unknown_key_beside_an_inline_discriminator_is_still_untouched():
    decoded = _decode_v(_Shirt | _Mug,
                        {"$type": "_Shirt", "size": "M", "when": "2026-08-08",
                         "nope": "2026-08-08"})

    assert decoded == {"$type": "_Shirt", "size": "M", "when": date(2026, 8, 8),
                       "nope": "2026-08-08"}


def test_absent_keys_stay_absent():
    """docs/decode.md: "Absent keys stay absent. Filling a missing key is what a default is for"."""
    assert struct_of(_Node).decode({}) == {}
    assert struct_of(_Address).decode({"city": "Madrid"}) == {"city": "Madrid"}


def test_a_decoded_dataclass_tree_never_shares_a_dict_with_the_input():
    """docs/decode.md: "nothing in `prepared` is an object inside `wire`"."""
    schema = struct_of(_Person)
    wire = {"name": "Ana", "address": {"city": "Madrid", "since": "2026-08-08"}}

    decoded = schema.decode(wire)

    assert decoded["address"] is not wire["address"]
    assert wire == {"name": "Ana", "address": {"city": "Madrid", "since": "2026-08-08"}}


def test_cyclic_input_data_raises_recursion_error():
    """docs/decode.md: "Cyclic input data raises `RecursionError`, as it does everywhere else in the core"."""
    cyclic: dict = {"children": []}
    cyclic["children"].append(cyclic)

    with pytest.raises(RecursionError):
        struct_of(_Node).decode(cyclic)


# ------------------------------------------------------------------------
# 11. Mutual recursion
# ------------------------------------------------------------------------

def test_mutual_recursion_decodes_each_class_at_its_own_depth():
    """A -> B -> A: each level uses the shape of the class that owns it, not the one above."""
    schema = struct_of(_Alpha)
    wire = {"on": "2026-08-08",
            "beta": {"at": "14:30",
                     "alpha": {"on": "2020-01-01",
                               "beta": {"at": "09:00:00", "alpha": None}}}}

    decoded = schema.decode(wire)

    assert decoded == {"on": date(2026, 8, 8),
                       "beta": {"at": time(14, 30),
                                "alpha": {"on": date(2020, 1, 1),
                                          "beta": {"at": time(9, 0), "alpha": None}}}}
    assert schema.build(decoded).beta.alpha.beta.at == time(9, 0)


def test_mutual_recursion_does_not_leak_one_levels_reading_into_the_next():
    """`_Alpha.on` is a date and `_Beta.at` is a time: a swap would decode neither."""
    decoded = struct_of(_Alpha).decode({"on": "14:30", "beta": {"at": "2026-08-08"}})

    assert decoded == {"on": "14:30", "beta": {"at": "2026-08-08"}}


def test_mutual_recursion_carries_a_wrapper_at_depth():
    schema = struct_of(make_dataclass("Root", [("node", _Alpha), ("terms", list[str] | list[int])]))

    decoded = schema.decode({"node": {"on": "2026-08-08"},
                             "terms": _wrap("list[int]", [1])})

    assert decoded == {"node": {"on": date(2026, 8, 8)},
                       "terms": _wrap("list[int]", [1])}


# ------------------------------------------------------------------------
# 12. Signature.decode
# ------------------------------------------------------------------------

def test_a_signature_decodes_its_parameters_the_way_a_struct_decodes_its_fields():
    def run(when: str | date, terms: list[str] | list[int], n: int = 1):
        return when, terms, n

    sig = signature_of(run)

    decoded = sig.decode({"when": _wrap("date", "2026-08-08"),
                          "terms": _wrap("list[int]", [1, 2])})

    assert decoded == {"when": date(2026, 8, 8), "terms": _wrap("list[int]", [1, 2])}
    assert sig.build(decoded) == {"when": date(2026, 8, 8), "terms": [1, 2], "n": 1}
    assert run(**sig.build(decoded)) == (date(2026, 8, 8), [1, 2], 1)


def test_a_signature_leaves_an_ambiguous_bare_parameter_as_it_came():
    def run(when: str | date, terms: list[str] | list[int]):
        return when, terms

    sig = signature_of(run)

    assert sig.decode({"when": "2026-08-08", "terms": ["a"]}) == {
        "when": "2026-08-08", "terms": ["a"]}


def test_a_signature_leaves_a_malformed_wrapper_for_build_to_report():
    def run(terms: list[str] | list[int]):
        return terms

    sig = signature_of(run)
    wire = {"terms": {"$type": "list[float]", "$value": [1]}}

    assert sig.decode(wire) == wire
    with pytest.raises(SchemaValueError) as error:
        sig.build(sig.decode(wire))
    assert error.value.path == ("terms", "$type")


def test_a_signature_omits_nothing_and_invents_nothing():
    """docs/decode.md: absent keys stay absent, unknown keys travel through."""
    def run(when: date, n: int = 1):
        return when, n

    sig = signature_of(run)

    assert sig.decode({}) == {}
    assert sig.decode({"nope": "2026-08-08"}) == {"nope": "2026-08-08"}


def test_a_signature_root_that_is_not_a_dict_is_returned_as_it_came():
    def run(when: date):
        return when

    sig = signature_of(run)

    assert sig.decode(None) is None
    assert sig.decode(["2026-08-08"]) == ["2026-08-08"]


def test_a_signature_decodes_a_dataclass_parameter_and_its_union_options():
    def run(item: _Shirt | _Mug, tags: list[date] | list[str]):
        return item, tags

    sig = signature_of(run)
    decoded = sig.decode({"item": {"$type": "_Shirt", "size": "M", "when": "2026-08-08"},
                          "tags": _wrap("list[date]", ["2026-08-08"])})

    assert decoded == {"item": {"$type": "_Shirt", "size": "M", "when": date(2026, 8, 8)},
                       "tags": _wrap("list[date]", [date(2026, 8, 8)])}
    assert sig.build(decoded) == {"item": _Shirt("M", date(2026, 8, 8)),
                                  "tags": [date(2026, 8, 8)]}


# ------------------------------------------------------------------------
# The pipeline has one direction
# ------------------------------------------------------------------------

@pytest.mark.parametrize("hint, value", [
    (str | date, date(2026, 8, 8)),
    (int | float, 3.0),
    (date | time, time(14, 30)),
    (_Role | _Status, _Role.ADMIN),
    (list[str] | list[int], _wrap("list[str]", ["a"])),
])
def test_decoding_an_already_exact_tree_changes_nothing(hint, value):
    """docs/decode.md: "nothing in an exact tree matches a portable spelling that isn't already its own"."""
    schema = _compile(hint)
    once = schema.decode({"v": value})

    assert once == {"v": value}
    assert schema.decode(once) == once

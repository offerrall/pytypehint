"""Contract tests for docs/decode.md — scalars and conversion by type.

`Struct.decode` and `Signature.decode` "prepare; they do not validate".  They
restore the four shapes a portable tree cannot carry — `Date`, `Time`,
`EnumShape`, and a whole `Float` that arrived as an `int` — "and nothing else".

This module freezes that promise one shape at a time, with a single wire
spelling per field.  Unions of colliding spellings, the `$type`/`$value`
wrapper, nested dataclasses and lists have their own files.

Every value decode declines to restore is checked twice: once for coming back
exactly as it came, and once for the error `build` raises over it, because
"decode never raises a schema error" — the diagnosis belongs to validation,
"one failure, reported once, in one place".
"""

from dataclasses import dataclass, make_dataclass
from datetime import date, time, timedelta, timezone
from enum import Enum, IntEnum, StrEnum

import pytest

from pytypehint import (
    SchemaTypeError, SchemaValueError, Struct, signature_of, struct_of,
)


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------

class _Status(Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class _Priority(Enum):
    LOW = 1
    HIGH = 2


class _Alias(Enum):
    A = 1
    B = 1          # an alias of A, not a member of its own


class _Cross(Enum):
    RED = "BLUE"   # docs/decode.md: "RED" is Cross.RED by name,
    BLUE = "RED"   # and Cross.BLUE by value.


class _Color(StrEnum):
    RED = "red"
    BLUE = "blue"


class _Size(IntEnum):
    SMALL = 1
    LARGE = 2


# A member whose name is one of the two reserved wrapper keys.  The name is
# still just a name, so it decodes like any other in payload position.
_Reserved = Enum("_Reserved", [("$type", 1), ("$value", 2), ("PLAIN", 3)])


class _Slug(str):
    """A str subclass, to prove `subclass ──▶ base type` never happens."""


@dataclass
class _User:
    name: str
    birthday: date


@dataclass
class _Post:
    slug: str


@dataclass
class _Booking:
    day: date


# Values built at run time so that `is` says something: a literal would be
# interned or cached and pass the assertion without decode doing anything.
_FRESH_STR = "a fresh %s" % "string"
_FRESH_INT = 10 ** 30 + 7
_FRESH_FLOAT = 3.0 + 0.0


def _schema_for(annotation) -> Struct:
    """A one-field struct, so one wire spelling can be watched in isolation."""
    return struct_of(make_dataclass("_Model", [("x", annotation)]))


# --------------------------------------------------------------------------
# 1. What decode does not touch: str, int, bool, None
# --------------------------------------------------------------------------

@pytest.mark.parametrize("annotation, value", [
    (str, _FRESH_STR),
    (str, ""),
    (int, _FRESH_INT),
    (int, 0),
    (bool, True),
    (bool, False),
    (str | None, None),
], ids=["str", "empty-str", "int", "zero", "true", "false", "none"])
def test_a_str_int_bool_or_none_comes_back_as_the_very_same_object(annotation, value):
    """"Every other value passes through unchanged." — docs/decode.md."""
    decoded = _schema_for(annotation).decode({"x": value})["x"]
    assert decoded is value
    assert type(decoded) is type(value)


@pytest.mark.parametrize("annotation, value", [
    (str, _FRESH_STR),
    (int, _FRESH_INT),
    (bool, True),
    (str | None, None),
], ids=["str", "int", "bool", "none"])
def test_a_scalar_decode_does_not_touch_still_builds(annotation, value):
    assert _schema_for(annotation).build({"x": value}) is not None


def test_a_str_field_holding_a_date_spelling_stays_a_str():
    """"A `str` field holding "2026-08-08" stays a `str`." — docs/decode.md."""
    assert struct_of(_Post).decode({"slug": "2026-08-08"}) == {"slug": "2026-08-08"}
    assert type(struct_of(_Post).decode({"slug": "2026-08-08"})["slug"]) is str
    assert struct_of(_Post).build({"slug": "2026-08-08"}) == _Post(slug="2026-08-08")


@pytest.mark.parametrize("annotation, value, message", [
    (int, "3", "x: expected int, got str"),
    (bool, "true", "x: expected bool, got str"),
    (bool, "false", "x: expected bool, got str"),
    (float, "3.5", "x: expected float, got str"),
    (date | None, "", "x: expected date | NoneType, got str"),
    (int | None, "null", "x: expected int | NoneType, got str"),
], ids=["str-to-int", "str-to-true", "str-to-false", "str-to-float",
        "empty-to-none", "null-to-none"])
def test_none_of_the_documented_coercions_happen(annotation, value, message):
    """The `"3" ──▶ int` / `"" ──▶ None` table of docs/decode.md, all refused."""
    schema = _schema_for(annotation)
    decoded = schema.decode({"x": value})["x"]
    assert decoded is value

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": decoded})
    assert str(error.value) == message


def test_an_empty_string_is_never_read_as_none():
    """`"" ──▶ None` is one of the readings that "never happen"."""
    for annotation in (str | None, date | None, time | None, _Status | None, float | None):
        decoded = _schema_for(annotation).decode({"x": ""})["x"]
        assert decoded == ""
        assert decoded is not None


def test_a_str_subclass_is_not_flattened_to_its_base_type():
    """`subclass ──▶ base type` is in the table of readings that never happen."""
    value = _Slug("hello")
    schema = _schema_for(str)

    decoded = schema.decode({"x": value})["x"]
    assert decoded is value
    assert type(decoded) is _Slug

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": decoded})
    assert str(error.value) == "x: expected str, got _Slug"


def test_decode_returns_a_fresh_dict_and_leaves_the_wire_tree_alone():
    """"`decode` never modifies the tree it is given." — docs/decode.md."""
    wire = {"name": "Ana", "birthday": "2000-05-17"}
    prepared = struct_of(_User).decode(wire)

    assert prepared is not wire
    assert wire == {"name": "Ana", "birthday": "2000-05-17"}
    assert prepared == {"name": "Ana", "birthday": date(2000, 5, 17)}
    assert struct_of(_User).build(prepared) == _User(name="Ana", birthday=date(2000, 5, 17))


def test_the_documented_user_example_reads_exactly_as_written():
    """The opening example of docs/decode.md, line for line."""
    schema = struct_of(_User)
    wire = {"name": "Ana", "birthday": "2000-05-17"}

    assert schema.decode(wire) == {"name": "Ana", "birthday": date(2000, 5, 17)}
    assert schema.build(schema.decode(wire)) == _User(name="Ana", birthday=date(2000, 5, 17))

    with pytest.raises(SchemaTypeError) as error:
        schema.build(wire)
    assert str(error.value) == "birthday: expected date, got str"


@pytest.mark.parametrize("value", [
    object(), 1, 1.5, True, None, [], {}, {"$type": "date"}, ("a",), b"x", 3j,
], ids=["object", "int", "float", "bool", "none", "list", "dict",
        "wrapper-ish", "tuple", "bytes", "complex"])
def test_decode_never_raises_however_foreign_the_value_is(value):
    """"Decode never raises a schema error." — docs/decode.md."""
    _schema_for(date).decode({"x": value})
    _schema_for(time).decode({"x": value})
    _schema_for(_Status).decode({"x": value})
    _schema_for(float).decode({"x": value})


# --------------------------------------------------------------------------
# 2. Float: a whole float may arrive as `3` rather than `3.0`
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value", [0, 1, 3, -5, 10 ** 20],
                         ids=["zero", "one", "three", "negative", "huge"])
def test_a_whole_number_that_arrived_as_an_int_becomes_a_float(value):
    """"a number; a whole float may arrive as `3` rather than `3.0`" — docs/decode.md."""
    decoded = _schema_for(float).decode({"x": value})["x"]
    assert type(decoded) is float
    assert decoded == float(value)
    assert _schema_for(float).build({"x": decoded}) is not None


def test_a_float_that_arrived_as_a_float_is_handed_back_untouched():
    decoded = _schema_for(float).decode({"x": _FRESH_FLOAT})["x"]
    assert decoded is _FRESH_FLOAT
    assert decoded == 3.0


@pytest.mark.parametrize("value", [True, False], ids=["true", "false"])
def test_bool_is_not_an_int_for_the_float_shape(value):
    """A `bool` is not a whole float that lost its fraction; it is a `bool`."""
    schema = _schema_for(float)
    decoded = schema.decode({"x": value})["x"]
    assert decoded is value
    assert type(decoded) is bool

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": decoded})
    assert str(error.value) == "x: expected float, got bool"


@pytest.mark.parametrize("value", ["3", "3.0", "3.5", "", "1e3"],
                         ids=["3", "3.0", "3.5", "empty", "exponent"])
def test_text_is_never_read_as_a_float(value):
    """`"3.5" ──▶ float` is coercion, and "stays outside the core"."""
    schema = _schema_for(float)
    decoded = schema.decode({"x": value})["x"]
    assert decoded is value

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": decoded})
    assert str(error.value) == "x: expected float, got str"


def test_only_a_float_field_reads_a_whole_number_that_way():
    """"The shape decides the reading; the text never does." — docs/decode.md."""
    assert _schema_for(float).decode({"x": 3})["x"] == 3.0
    assert type(_schema_for(float).decode({"x": 3})["x"]) is float

    assert _schema_for(int).decode({"x": _FRESH_INT})["x"] is _FRESH_INT
    assert type(_schema_for(int).decode({"x": 3})["x"]) is int

    assert _schema_for(str).decode({"x": 3})["x"] == 3
    with pytest.raises(SchemaTypeError) as error:
        _schema_for(str).build({"x": 3})
    assert str(error.value) == "x: expected str, got int"


def test_the_int_field_does_not_read_a_float_the_other_way_round():
    """Only the `Float` direction was lost by the transport, so only it is restored."""
    schema = _schema_for(int)
    decoded = schema.decode({"x": 3.0})["x"]
    assert type(decoded) is float

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": decoded})
    assert str(error.value) == "x: expected int, got float"


def test_an_int_beyond_the_float_range_is_handed_back_for_build_to_report():
    """"a value decode cannot restore is handed back exactly as it came" — docs/decode.md."""
    schema = _schema_for(float)
    huge = 10 ** 400

    # An int too large to be a float is not a whole float that lost its
    # fraction: there is nothing to restore.  `float()` would raise OverflowError
    # on it, and docs/decode.md names RecursionError on cyclic input as the only
    # exception to "decode never raises", so the int has to travel on untouched
    # and `Float._check` — which refuses an infinity anyway — reports it.
    decoded = schema.decode({"x": huge})["x"]
    assert decoded is huge

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": decoded})
    assert str(error.value) == "x: expected float, got int"


def test_an_int_enum_member_is_not_flattened_into_the_float_it_could_become():
    """`subclass ──▶ base type` never happens, whatever the runtime type allows."""
    schema = _schema_for(float)
    decoded = schema.decode({"x": _Size.SMALL})["x"]
    assert decoded is _Size.SMALL

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": decoded})
    assert str(error.value) == "x: expected float, got _Size"


def test_decoding_an_already_exact_float_is_a_no_op():
    """"nothing in an exact tree matches a portable spelling that isn't already its own"."""
    schema = _schema_for(float)
    once = schema.decode({"x": 3})
    assert schema.decode(once) == once == {"x": 3.0}


# --------------------------------------------------------------------------
# 3. Date: the canonical spelling only
# --------------------------------------------------------------------------

@pytest.mark.parametrize("wire, expected", [
    ("2026-08-08", date(2026, 8, 8)),
    ("2000-05-17", date(2000, 5, 17)),
    ("0001-01-01", date(1, 1, 1)),
    ("9999-12-31", date(9999, 12, 31)),
    ("2024-02-29", date(2024, 2, 29)),
], ids=["docs", "user-example", "min", "max", "leap-day"])
def test_a_canonical_iso_date_becomes_a_date(wire, expected):
    """`Date` travels as `"YYYY-MM-DD"`, and decode restores exactly that."""
    schema = _schema_for(date)
    decoded = schema.decode({"x": wire})["x"]
    assert type(decoded) is date
    assert decoded == expected
    assert schema.build({"x": decoded}) is not None


@pytest.mark.parametrize("wire", [
    "20260808",
    "2026-W32-6",
    "2026-08-08T10:00",
    "2026/08/08",
    "2026-8-8",
    "",
    "hello",
    "2026-08-08 ",
    " 2026-08-08",
    "26-08-08",
    "2026-08-08Z",
    "+2026-08-08",
], ids=["basic", "week-date", "datetime", "slashes", "unpadded", "empty",
        "text", "trailing-space", "leading-space", "two-digit-year",
        "zulu", "signed"])
def test_anything_but_the_canonical_iso_date_stays_a_str(wire):
    """The rejected column of the Date row in docs/decode.md: "left as `str`"."""
    schema = _schema_for(date)
    decoded = schema.decode({"x": wire})["x"]
    assert decoded is wire
    assert type(decoded) is str

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": decoded})
    assert str(error.value) == "x: expected date, got str"


@pytest.mark.parametrize("wire", ["2026-02-31", "2025-02-29", "2026-13-01",
                                  "2026-04-31", "2026-00-10", "2026-01-00"],
                         ids=["docs", "not-a-leap-year", "month-13",
                              "april-31", "month-0", "day-0"])
def test_a_canonical_spelling_that_names_no_real_day_is_left_as_a_str(wire):
    """"A canonical spelling that names no real day — "2026-02-31" — is left as `str`"."""
    schema = _schema_for(date)
    decoded = schema.decode({"x": wire})["x"]
    assert decoded is wire

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": decoded})
    assert str(error.value) == "x: expected date, got str"


def test_decoding_an_already_decoded_date_is_a_no_op():
    """"For a value already in exact Python ... decoding it is harmless." — docs/decode.md."""
    day = date(2026, 8, 8)
    schema = _schema_for(date)
    assert schema.decode({"x": day})["x"] is day
    assert schema.decode(schema.decode({"x": "2026-08-08"})) == {"x": day}


def test_the_documented_booking_example_reads_exactly_as_written():
    """The Booking block of docs/decode.md, line for line."""
    schema = struct_of(_Booking)
    assert schema.decode({"day": "2026-08-08"}) == {"day": date(2026, 8, 8)}
    assert schema.decode({"day": "hello"}) == {"day": "hello"}

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"day": "hello"})
    assert str(error.value) == "day: expected date, got str"


# --------------------------------------------------------------------------
# 4. Time: "HH:MM" or "HH:MM:SS", and the spellings the shape will refuse
# --------------------------------------------------------------------------

@pytest.mark.parametrize("wire, expected", [
    ("14:30", time(14, 30)),
    ("14:30:00", time(14, 30)),
    ("00:00", time(0, 0)),
    ("00:00:00", time(0, 0)),
    ("23:59:59", time(23, 59, 59)),
    ("09:05:07", time(9, 5, 7)),
], ids=["hh-mm", "hh-mm-ss", "midnight", "midnight-ss", "last-second", "padded"])
def test_a_canonical_time_becomes_a_time(wire, expected):
    """`Time` travels as `"HH:MM"` or `"HH:MM:SS"` — docs/decode.md."""
    schema = _schema_for(time)
    decoded = schema.decode({"x": wire})["x"]
    assert type(decoded) is time
    assert decoded == expected
    assert schema.build({"x": decoded}) is not None


@pytest.mark.parametrize("wire, expected", [
    ("10:00:00.5", time(10, 0, 0, 500000)),
    ("10:00:00.05", time(10, 0, 0, 50000)),
    ("10:00:00.123", time(10, 0, 0, 123000)),
    ("10:00:00.1234", time(10, 0, 0, 123400)),
    ("10:00:00.12345", time(10, 0, 0, 123450)),
    ("10:00:00.123456", time(10, 0, 0, 123456)),
], ids=["1-digit", "2-digits", "3-digits", "4-digits", "5-digits", "6-digits"])
def test_a_sub_second_time_is_read_so_the_shape_reports_its_own_rule(wire, expected):
    """`{"at": "10:00:00.5"} ──▶ time(10, 0, 0, 500000)` — docs/decode.md."""
    schema = _schema_for(time)
    decoded = schema.decode({"x": wire})["x"]
    assert type(decoded) is time
    assert decoded == expected

    with pytest.raises(SchemaValueError) as error:
        schema.build({"x": decoded})
    assert str(error.value) == f"x: time precision is limited to whole seconds: {expected}"


def test_more_than_six_fractional_digits_is_not_a_time_spelling_at_all():
    """Beyond microsecond precision there is no `time` to produce, so the str stands."""
    schema = _schema_for(time)
    decoded = schema.decode({"x": "10:00:00.1234567"})["x"]
    assert decoded == "10:00:00.1234567"

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": decoded})
    assert str(error.value) == "x: expected time, got str"


@pytest.mark.parametrize("wire, offset, shown", [
    ("10:00:00+02:00", timezone(timedelta(hours=2)), "10:00:00+02:00"),
    ("10:00:00-05:00", timezone(timedelta(hours=-5)), "10:00:00-05:00"),
    ("10:00:00Z", timezone.utc, "10:00:00+00:00"),
    ("10:00+02:00", timezone(timedelta(hours=2)), "10:00:00+02:00"),
], ids=["plus", "minus", "zulu", "hh-mm-plus"])
def test_an_aware_time_is_read_so_the_shape_reports_must_be_naive(wire, offset, shown):
    """`{"at": "10:00:00+02:00"} ──▶ time(10, 0, tzinfo=…)` — docs/decode.md."""
    schema = _schema_for(time)
    decoded = schema.decode({"x": wire})["x"]
    assert type(decoded) is time
    assert decoded.tzinfo == offset
    assert decoded == time(10, 0, tzinfo=offset)

    with pytest.raises(SchemaValueError) as error:
        schema.build({"x": decoded})
    assert str(error.value) == f"x: must be naive (no tzinfo): {shown}"


@pytest.mark.parametrize("wire", [
    "2020",
    "1430",
    "143000",
    "25:00",
    "24:00",
    "",
    "hello",
    "9:30",
    "14-30",
    "14:30:",
    "14:30:00.",
    "T14:30",
    "14:30:60",
    "14:60",
], ids=["four-digits", "basic-hhmm", "basic-hhmmss", "hour-25", "hour-24",
        "empty", "text", "unpadded-hour", "dashes", "trailing-colon",
        "empty-fraction", "designator", "second-60", "minute-60"])
def test_anything_but_a_canonical_time_spelling_stays_a_str(wire):
    """The rejected column of the Time row in docs/decode.md, plus impossible clocks."""
    schema = _schema_for(time)
    decoded = schema.decode({"x": wire})["x"]
    assert decoded is wire
    assert type(decoded) is str

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": decoded})
    assert str(error.value) == "x: expected time, got str"


def test_the_date_and_time_grammars_never_overlap():
    """"they are disjoint — one carries `-` and no `:`, the other the reverse"."""
    assert _schema_for(date).decode({"x": "20200101"})["x"] == "20200101"
    assert _schema_for(time).decode({"x": "20200101"})["x"] == "20200101"
    assert _schema_for(time).decode({"x": "2020"})["x"] == "2020"
    assert _schema_for(date).decode({"x": "14:30"})["x"] == "14:30"
    assert _schema_for(time).decode({"x": "2026-08-08"})["x"] == "2026-08-08"


@pytest.mark.parametrize("annotation, wire, name", [
    (date, "٢٠٢٦-٠٨-٠٨", "date"),
    (time, "١٤:٣٠", "time"),
], ids=["date", "time"])
def test_a_spelling_made_of_non_ascii_digits_stays_a_str(annotation, wire, name):
    """The accepted spellings "are fixed": digits that are not ASCII name no day or hour."""
    schema = _schema_for(annotation)
    decoded = schema.decode({"x": wire})["x"]
    assert decoded is wire

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": decoded})
    assert str(error.value) == f"x: expected {name}, got str"


def test_decoding_an_already_decoded_time_is_a_no_op():
    at = time(14, 30)
    schema = _schema_for(time)
    assert schema.decode({"x": at})["x"] is at
    assert schema.decode(schema.decode({"x": "14:30:00"})) == {"x": at}


# --------------------------------------------------------------------------
# 5. Enums travel by member name
# --------------------------------------------------------------------------

def test_an_enum_member_name_decodes_to_the_member_itself():
    """"Decode returns the member itself, not a copy, so `is` comparisons hold"."""
    schema = _schema_for(_Status)
    assert schema.decode({"status": "ACTIVE"}) == {"status": "ACTIVE"}   # unknown key
    assert schema.decode({"x": "ACTIVE"})["x"] is _Status.ACTIVE
    assert schema.decode({"x": "CLOSED"})["x"] is _Status.CLOSED
    assert schema.build({"x": schema.decode({"x": "ACTIVE"})["x"]}) is not None


@pytest.mark.parametrize("wire", ["active", "closed", "Active", "ACTIVE ", "",
                                  "OPEN", "value", "name"],
                         ids=["value", "other-value", "title-case", "trailing-space",
                              "empty", "absent-name", "value-word", "name-word"])
def test_a_name_no_member_carries_stays_a_str(wire):
    """"The name, not the value" — anything else is handed back for `build` to report."""
    schema = _schema_for(_Status)
    decoded = schema.decode({"x": wire})["x"]
    assert decoded is wire

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": decoded})
    assert str(error.value) == "x: expected _Status, got str"


def test_an_enum_with_numeric_values_is_still_keyed_by_name():
    """"a value may be a tuple, an object, or anything else a portable tree cannot carry"."""
    schema = _schema_for(_Priority)
    assert schema.decode({"x": "LOW"})["x"] is _Priority.LOW
    assert schema.decode({"x": "HIGH"})["x"] is _Priority.HIGH

    assert schema.decode({"x": 1})["x"] == 1
    assert type(schema.decode({"x": 1})["x"]) is int
    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": 1})
    assert str(error.value) == "x: expected _Priority, got int"

    assert schema.decode({"x": "1"})["x"] == "1"
    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": "1"})
    assert str(error.value) == "x: expected _Priority, got str"


def test_an_alias_resolves_to_the_member_it_aliases():
    """"An alias resolves to the member it aliases, because that is what the enum does"."""
    schema = _schema_for(_Alias)
    assert schema.decode({"x": "B"})["x"] is _Alias.A
    assert schema.decode({"x": "A"})["x"] is _Alias.A
    assert schema.build({"x": schema.decode({"x": "B"})["x"]}) is not None


@pytest.mark.parametrize("wire, member", [("RED", _Cross.RED), ("BLUE", _Cross.BLUE)],
                         ids=["red", "blue"])
def test_a_crossed_enum_is_read_by_name_and_never_by_value(wire, member):
    """""RED" is Cross.RED by name, and Cross.BLUE by value." — decode takes the name."""
    decoded = _schema_for(_Cross).decode({"x": wire})["x"]
    assert decoded is member
    assert decoded.name == wire
    assert decoded.value != wire


@pytest.mark.parametrize("enum_cls, name, member, wrong", [
    (_Color, "RED", _Color.RED, "red"),
    (_Size, "SMALL", _Size.SMALL, 1),
], ids=["strenum", "intenum"])
def test_a_strenum_or_intenum_travels_by_name_like_any_other_enum(enum_cls, name, member, wrong):
    """A `StrEnum` member equals its value, but decode still keys on the name."""
    schema = _schema_for(enum_cls)
    assert schema.decode({"x": name})["x"] is member

    decoded = schema.decode({"x": wrong})["x"]
    assert type(decoded) is type(wrong)
    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": decoded})
    assert str(error.value) == f"x: expected {enum_cls.__name__}, got {type(wrong).__name__}"


@pytest.mark.parametrize("name", ["$type", "$value", "PLAIN"],
                         ids=["type-key", "value-key", "plain"])
def test_a_member_named_like_a_reserved_wrapper_key_decodes_in_payload_position(name):
    """A reserved key is only reserved for a dict; as a payload it is an ordinary name."""
    schema = _schema_for(_Reserved)
    decoded = schema.decode({"x": name})["x"]
    assert decoded is _Reserved[name]
    assert decoded.name == name
    assert schema.build({"x": decoded}).x is _Reserved[name]


def test_decoding_an_already_decoded_enum_member_is_a_no_op():
    schema = _schema_for(_Status)
    assert schema.decode({"x": _Status.ACTIVE})["x"] is _Status.ACTIVE


# --------------------------------------------------------------------------
# 6. Optional: `X | None`, two disjoint portable spellings
# --------------------------------------------------------------------------

@pytest.mark.parametrize("annotation, wire, expected", [
    (date | None, "2026-08-08", date(2026, 8, 8)),
    (time | None, "14:30", time(14, 30)),
    (time | None, "14:30:00", time(14, 30)),
    (_Status | None, "ACTIVE", _Status.ACTIVE),
    (float | None, 3, 3.0),
    (float | None, 3.0, 3.0),
], ids=["date", "time", "time-ss", "enum", "whole-float", "float"])
def test_an_optional_field_decodes_its_one_non_none_option(annotation, wire, expected):
    """`X | None` is a union of disjoint portable spellings, so the schema still decides."""
    schema = _schema_for(annotation)
    decoded = schema.decode({"x": wire})["x"]
    assert decoded == expected
    assert type(decoded) is type(expected)
    assert schema.build({"x": decoded}) is not None


@pytest.mark.parametrize("annotation", [date | None, time | None, _Status | None, float | None],
                         ids=["date", "time", "enum", "float"])
def test_an_explicit_none_stays_none_in_an_optional_field(annotation):
    schema = _schema_for(annotation)
    assert schema.decode({"x": None})["x"] is None
    assert schema.build({"x": None}) is not None


@pytest.mark.parametrize("annotation", [date | None, time | None, _Status | None, float | None],
                         ids=["date", "time", "enum", "float"])
def test_an_absent_key_stays_absent_and_decode_never_runs_a_recipe(annotation):
    """"Absent keys stay absent. ... Decode never runs a recipe." — docs/decode.md."""
    model = make_dataclass("_Model", [("x", annotation, None)])  # a default is waiting
    assert struct_of(model).decode({}) == {}
    assert struct_of(model).resolve({}) == {"x": None}


@pytest.mark.parametrize("annotation, wire, message", [
    (date | None, "hello", "x: expected date | NoneType, got str"),
    (date | None, "", "x: expected date | NoneType, got str"),
    (date | None, "2026-02-31", "x: expected date | NoneType, got str"),
    (time | None, "2020", "x: expected time | NoneType, got str"),
    (time | None, "", "x: expected time | NoneType, got str"),
    (_Status | None, "active", "x: expected _Status | NoneType, got str"),
    (_Status | None, "", "x: expected _Status | NoneType, got str"),
    (float | None, "3", "x: expected float | NoneType, got str"),
    (float | None, True, "x: expected float | NoneType, got bool"),
], ids=["date-text", "date-empty", "date-impossible", "time-basic", "time-empty",
        "enum-value", "enum-empty", "float-text", "float-bool"])
def test_an_optional_field_hands_back_what_it_cannot_restore(annotation, wire, message):
    """The `None` option never catches a value the other option refused."""
    schema = _schema_for(annotation)
    decoded = schema.decode({"x": wire})["x"]
    assert decoded is wire
    assert decoded is not None

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": decoded})
    assert str(error.value) == message


# --------------------------------------------------------------------------
# 7. Signature.decode, the same contract over parameters
# --------------------------------------------------------------------------

def _sig_for(annotation, default=None, *, with_default=False):
    if with_default:
        def fn(x=default):
            return x
        fn.__annotations__["x"] = annotation
    else:
        def fn(x):
            return x
        fn.__annotations__["x"] = annotation
    return signature_of(fn)


@pytest.mark.parametrize("annotation, wire, expected", [
    (date, "2026-08-08", date(2026, 8, 8)),
    (time, "14:30", time(14, 30)),
    (time, "14:30:00", time(14, 30)),
    (_Status, "ACTIVE", _Status.ACTIVE),
    (float, 3, 3.0),
    (str, "2026-08-08", "2026-08-08"),
    (int, 3, 3),
    (bool, True, True),
], ids=["date", "time", "time-ss", "enum", "whole-float", "str", "int", "bool"])
def test_signature_decode_restores_a_parameter_the_same_way_a_field_is_restored(
        annotation, wire, expected):
    sig = _sig_for(annotation)
    decoded = sig.decode({"x": wire})["x"]
    assert decoded == expected
    assert type(decoded) is type(expected)
    assert sig.build({"x": decoded}) == {"x": expected}


@pytest.mark.parametrize("annotation, wire, message", [
    (date, "hello", "x: expected date, got str"),
    (date, "20260808", "x: expected date, got str"),
    (date, "2026-02-31", "x: expected date, got str"),
    (time, "1430", "x: expected time, got str"),
    (time, "25:00", "x: expected time, got str"),
    (_Status, "active", "x: expected _Status, got str"),
    (float, "3", "x: expected float, got str"),
    (float, True, "x: expected float, got bool"),
], ids=["date-text", "date-basic", "date-impossible", "time-basic", "time-25",
        "enum-value", "float-text", "float-bool"])
def test_signature_decode_hands_back_what_it_cannot_restore_for_build_to_report(
        annotation, wire, message):
    sig = _sig_for(annotation)
    decoded = sig.decode({"x": wire})["x"]
    assert decoded is wire

    with pytest.raises(SchemaTypeError) as error:
        sig.build({"x": decoded})
    assert str(error.value) == message


def test_signature_decode_reports_a_sub_second_and_an_aware_time_through_build():
    sig = _sig_for(time)
    assert sig.decode({"x": "10:00:00.5"})["x"] == time(10, 0, 0, 500000)
    with pytest.raises(SchemaValueError) as error:
        sig.build(sig.decode({"x": "10:00:00.5"}))
    assert str(error.value) == "x: time precision is limited to whole seconds: 10:00:00.500000"

    assert sig.decode({"x": "10:00:00Z"})["x"] == time(10, 0, tzinfo=timezone.utc)
    with pytest.raises(SchemaValueError) as error:
        sig.build(sig.decode({"x": "10:00:00Z"}))
    assert str(error.value) == "x: must be naive (no tzinfo): 10:00:00+00:00"


@pytest.mark.parametrize("annotation, default", [
    (date, date(2026, 8, 8)),
    (time, time(14, 30)),
    (_Status, _Status.ACTIVE),
    (float, 1.0),
    (str, "s"),
], ids=["date", "time", "enum", "float", "str"])
def test_a_parameter_with_a_default_is_still_absent_after_decode(annotation, default):
    """"Filling a missing key is what a default is for, and `resolve` serves it"."""
    sig = _sig_for(annotation, default, with_default=True)
    assert sig.decode({}) == {}
    assert sig.resolve({}) == {"x": default}
    assert sig.build({}) == {"x": default}


def test_a_signature_decodes_every_parameter_it_knows_and_leaves_the_rest():
    def book(day: date, at: time, status: _Status, ratio: float, note: str):
        return day, at, status, ratio, note

    sig = signature_of(book)
    wire = {"day": "2026-08-08", "at": "14:30", "status": "CLOSED",
            "ratio": 2, "note": "2026-08-08"}
    assert sig.decode(wire) == {
        "day": date(2026, 8, 8), "at": time(14, 30), "status": _Status.CLOSED,
        "ratio": 2.0, "note": "2026-08-08",
    }
    assert wire["day"] == "2026-08-08"
    assert sig.build(sig.decode(wire)) == sig.decode(wire)


def test_a_signature_optional_parameter_follows_the_same_rules():
    def fn(day: date | None = None):
        return day

    sig = signature_of(fn)
    assert sig.decode({}) == {}
    assert sig.decode({"day": None}) == {"day": None}
    assert sig.decode({"day": "2026-08-08"}) == {"day": date(2026, 8, 8)}
    assert sig.decode({"day": ""}) == {"day": ""}

    with pytest.raises(SchemaTypeError) as error:
        sig.build({"day": ""})
    assert str(error.value) == "day: expected date | NoneType, got str"

from datetime import date, datetime, time, timedelta, timezone
from enum import Enum, IntEnum, StrEnum

import pytest

from pytypehint.shapes import Bool, Date, Float, Int, NoneShape, Str, Time


class Color(Enum):
    RED = 1


class SColor(StrEnum):
    RED = "red"


class IColor(IntEnum):
    ONE = 1


WRONG_FOR_INT = [1.0, True, False, "1", None, [], (), {}, 1j, b"x", date(2020, 1, 1)]
WRONG_FOR_FLOAT = [1, True, "1.0", None, [], (), 1j, b"x", date(2020, 1, 1)]
WRONG_FOR_STR = [1, 1.0, True, None, [], (), b"x", SColor.RED, Color.RED]
WRONG_FOR_BOOL = [1, 0, "true", "", None, [], 1.0]
WRONG_FOR_DATE = [datetime(2020, 1, 1), "2020-01-01", 0, 1.0, None, True]
WRONG_FOR_NONE = [0, "", False, [], (), {}, 1.0, "None"]


@pytest.mark.parametrize("v", WRONG_FOR_INT)
def test_int_rejects_every_wrong_type(v):
    with pytest.raises(TypeError, match="expected int"):
        Int()._check(v)


@pytest.mark.parametrize("v", WRONG_FOR_FLOAT)
def test_float_rejects_every_wrong_type(v):
    with pytest.raises(TypeError, match="expected float"):
        Float()._check(v)


@pytest.mark.parametrize("v", WRONG_FOR_STR)
def test_str_rejects_every_wrong_type(v):
    with pytest.raises(TypeError, match="expected str"):
        Str()._check(v)


@pytest.mark.parametrize("v", WRONG_FOR_BOOL)
def test_bool_rejects_every_wrong_type(v):
    with pytest.raises(TypeError, match="expected bool"):
        Bool()._check(v)


@pytest.mark.parametrize("v", WRONG_FOR_DATE)
def test_date_rejects_every_wrong_type(v):
    with pytest.raises(TypeError, match="expected date"):
        Date()._check(v)


@pytest.mark.parametrize("v", WRONG_FOR_NONE)
def test_none_rejects_everything_but_none(v):
    with pytest.raises(TypeError, match="expected None"):
        NoneShape()._check(v)


@pytest.mark.parametrize("v", [datetime(2020, 1, 1), "09:00", 0, 1.0, None, True])
def test_time_rejects_every_wrong_type(v):
    with pytest.raises(TypeError, match="expected time"):
        Time()._check(v)


@pytest.mark.parametrize("aware", [
    time(9, 0, tzinfo=timezone.utc),
    time(0, 0, tzinfo=timezone.utc),
    time(23, 59, tzinfo=timezone(timedelta(hours=5))),
])
def test_time_rejects_aware_with_valueerror(aware):
    with pytest.raises(ValueError, match="must be naive"):
        Time()._check(aware)


def test_int_accepts_only_plain_int():
    Int()._check(0)
    Int()._check(-999)
    Int()._check(2 ** 63)


def test_float_accepts_only_plain_float():
    Float()._check(0.0)
    Float()._check(-1.5)


def test_str_accepts_only_plain_str():
    Str()._check("")
    Str()._check("anything")


def test_bool_accepts_both_bools():
    Bool()._check(True)
    Bool()._check(False)


def test_none_accepts_none():
    NoneShape()._check(None)


def test_intenum_member_is_not_int():
    with pytest.raises(TypeError, match="expected int"):
        Int()._check(IColor.ONE)


class Custom:
    pass


EXOTIC = [Custom(), frozenset(), set(), range(3), memoryview(b"x"), bytearray(b"x"), 3 + 4j]


@pytest.mark.parametrize("v", EXOTIC)
def test_int_rejects_exotic_objects(v):
    with pytest.raises(TypeError, match="expected int"):
        Int()._check(v)


@pytest.mark.parametrize("v", EXOTIC)
def test_str_rejects_exotic_objects(v):
    with pytest.raises(TypeError, match="expected str"):
        Str()._check(v)


@pytest.mark.parametrize("v", EXOTIC + [1, 1.0, "x", None])
def test_bool_rejects_everything_non_bool(v):
    with pytest.raises(TypeError, match="expected bool"):
        Bool()._check(v)


@pytest.mark.parametrize("v", EXOTIC + [date(2020, 1, 1), time(9, 0)])
def test_float_rejects_exotic_and_temporal(v):
    with pytest.raises(TypeError, match="expected float"):
        Float()._check(v)


@pytest.mark.parametrize("v", [time(9, 0), datetime(2020, 1, 1), date(2020, 1, 1)])
def test_date_and_time_do_not_cross(v):
    if type(v) is not date:
        with pytest.raises(TypeError, match="expected date"):
            Date()._check(v)
    if type(v) is not time:
        with pytest.raises(TypeError, match="expected time"):
            Time()._check(v)


@pytest.mark.parametrize("member", [Color.RED, SColor.RED, IColor.ONE])
def test_enum_members_are_not_their_underlying_types(member):
    with pytest.raises(TypeError):
        Str()._check(member)
    with pytest.raises(TypeError):
        Int()._check(member)


@pytest.mark.parametrize("v", [0, 1, -1, 2 ** 100])
def test_int_accepts_all_plain_ints(v):
    Int()._check(v)


@pytest.mark.parametrize("v", [0.0, -0.0, 1e-300, 1e300, 3.14159])
def test_float_accepts_all_finite_floats(v):
    Float()._check(v)


@pytest.mark.parametrize("v", ["", "x", "unicode: café ☕", "\n\t", "a" * 10000])
def test_str_accepts_all_strings(v):
    Str()._check(v)

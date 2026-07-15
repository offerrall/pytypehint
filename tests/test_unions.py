from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated

import pytest

from pytypehint import Max, Min, struct_of
from pytypehint.shapes import Int, Str


# --------------------------------------------------------------------------
# int | str: routing by exact type, with a default
# --------------------------------------------------------------------------

@dataclass
class IntOrStr:
    v: int | str = 0


@pytest.mark.parametrize("value", [0, 1, -99, 2 ** 40])
def test_int_or_str_routes_int(value):
    assert struct_of(IntOrStr).resolve({"v": value}) == {"v": value}


@pytest.mark.parametrize("value", ["", "hello", "123"])
def test_int_or_str_routes_str(value):
    assert struct_of(IntOrStr).resolve({"v": value}) == {"v": value}


@pytest.mark.parametrize("value", [1.5, True, None, [], (), b"x"])
def test_int_or_str_rejects_other_types(value):
    with pytest.raises(TypeError, match=r"expected int \| str, got"):
        struct_of(IntOrStr).resolve({"v": value})


def test_int_or_str_missing_uses_int_default():
    assert struct_of(IntOrStr).resolve({}) == {"v": 0}


@dataclass
class StrDefault:
    v: int | str = "hello"


def test_union_default_can_be_the_str_arm():
    assert struct_of(StrDefault).resolve({}) == {"v": "hello"}
    assert struct_of(StrDefault).resolve({"v": 5}) == {"v": 5}


def test_str_int_order_is_equivalent_to_int_str():
    @dataclass
    class A:
        v: int | str = 0

    @dataclass
    class B:
        v: str | int = 0

    a = struct_of(A).fields[0]
    b = struct_of(B).fields[0]
    assert {s.pytype for s in a.shape} == {s.pytype for s in b.shape}
    assert struct_of(A).resolve({"v": "x"}) == struct_of(B).resolve({"v": "x"})


# --------------------------------------------------------------------------
# Optionality: X | None
# --------------------------------------------------------------------------

@dataclass
class OptInt:
    v: int | None = None


def test_optional_accepts_none():
    assert struct_of(OptInt).resolve({"v": None}) == {"v": None}


def test_optional_accepts_value():
    assert struct_of(OptInt).resolve({"v": 5}) == {"v": 5}


def test_optional_missing_uses_none_default():
    assert struct_of(OptInt).resolve({}) == {"v": None}


def test_optional_rejects_foreign_type():
    with pytest.raises(TypeError, match=r"expected int \| NoneType, got str"):
        struct_of(OptInt).resolve({"v": "x"})


@dataclass
class OptIntValueDefault:
    v: int | None = 42


def test_optional_default_can_be_the_value_arm():
    assert struct_of(OptIntValueDefault).resolve({}) == {"v": 42}
    assert struct_of(OptIntValueDefault).resolve({"v": None}) == {"v": None}


# --------------------------------------------------------------------------
# Three-way union
# --------------------------------------------------------------------------

@dataclass
class Tri:
    v: int | str | None = None


@pytest.mark.parametrize("value", [7, "seven", None])
def test_three_way_union_routes_each_arm(value):
    assert struct_of(Tri).resolve({"v": value}) == {"v": value}


@pytest.mark.parametrize("value", [1.0, True, []])
def test_three_way_union_rejects_others(value):
    with pytest.raises(TypeError):
        struct_of(Tri).resolve({"v": value})


# --------------------------------------------------------------------------
# bool | int: distinct pytypes, no crossing
# --------------------------------------------------------------------------

@dataclass
class BoolOrInt:
    v: bool | int = 0


def test_bool_and_int_are_distinct_arms():
    assert struct_of(BoolOrInt).resolve({"v": True}) == {"v": True}
    assert struct_of(BoolOrInt).resolve({"v": 5}) == {"v": 5}


# --------------------------------------------------------------------------
# Per-option constraints: Annotated inside one arm
# --------------------------------------------------------------------------

@dataclass
class ConstrainedArm:
    v: Annotated[int, Min(0), Max(10)] | str = 0


def test_constraint_applies_to_matching_arm():
    assert struct_of(ConstrainedArm).resolve({"v": 5}) == {"v": 5}
    with pytest.raises(ValueError, match="too large"):
        struct_of(ConstrainedArm).resolve({"v": 99})


def test_other_arm_is_unconstrained():
    assert struct_of(ConstrainedArm).resolve({"v": "anything at all"}) == {"v": "anything at all"}


def test_type_metadata_on_whole_union_is_rejected():
    @dataclass
    class M:
        v: Annotated[int | str, Min(0)] = 0

    with pytest.raises(TypeError, match="metadata on a union of multiple types must go per option"):
        struct_of(M)


# --------------------------------------------------------------------------
# Union with a dataclass arm
# --------------------------------------------------------------------------

@dataclass
class Inner:
    n: int = 0


@dataclass
class StructOrInt:
    v: Inner | int = 0


def test_union_rejects_dataclass_instance():
    inner = Inner(n=3)
    with pytest.raises(TypeError, match="v: expected dict, got Inner instance"):
        struct_of(StructOrInt).resolve({"v": inner})


def test_union_routes_scalar_arm():
    assert struct_of(StructOrInt).resolve({"v": 7}) == {"v": 7}


def test_union_single_struct_accepts_dict():
    assert struct_of(StructOrInt).resolve({"v": {"n": 3}}) == {"v": {"n": 3}}


# --------------------------------------------------------------------------
# Union of two dataclasses: a dict is ambiguous
# --------------------------------------------------------------------------

@dataclass
class A:
    x: int = 0


@dataclass
class B:
    y: int = 0


@dataclass
class AorB:
    v: A | B = field(default_factory=A)


def test_two_struct_union_rejects_instance():
    a = A(x=1)
    with pytest.raises(TypeError, match="v: expected dict, got A instance"):
        struct_of(AorB).resolve({"v": a})


def test_two_struct_union_rejects_ambiguous_dict():
    with pytest.raises(TypeError, match=r'ambiguous dict: field accepts A \| B — add "\$type" naming the variant'):
        struct_of(AorB).resolve({"v": {"x": 1}})


# --------------------------------------------------------------------------
# Enum arm
# --------------------------------------------------------------------------

class Role(Enum):
    ADMIN = "admin"
    USER = "user"


@dataclass
class OptRole:
    v: Role | None = None


def test_enum_union_routes_member():
    assert struct_of(OptRole).resolve({"v": Role.ADMIN}) == {"v": Role.ADMIN}


def test_enum_union_routes_none():
    assert struct_of(OptRole).resolve({"v": None}) == {"v": None}


def test_enum_union_rejects_raw_value():
    with pytest.raises(TypeError, match=r"expected Role \| NoneType, got str"):
        struct_of(OptRole).resolve({"v": "admin"})


# --------------------------------------------------------------------------
# Illegal unions, caught at compile time
# --------------------------------------------------------------------------

def test_duplicate_option_types_rejected():
    @dataclass
    class M:
        v: Annotated[int, Min(0)] | int = 0

    with pytest.raises(ValueError, match="duplicate option types in shape"):
        struct_of(M)


def test_none_alone_rejected():
    @dataclass
    class M:
        v: None = None

    with pytest.raises(TypeError, match="None must be accompanied by another option"):
        struct_of(M)


def test_default_must_match_one_arm():
    @dataclass
    class M:
        v: int | str = 1.5

    with pytest.raises(TypeError, match=r"Field 'v': default expected int \| str, got float"):
        struct_of(M)


def test_list_item_union_compiles():
    @dataclass
    class M:
        xs: list[int | str] = field(default_factory=list)

    assert type(struct_of(M).fields[0].shape[0].item) is tuple


# --------------------------------------------------------------------------
# Values travel by reference through a union
# --------------------------------------------------------------------------

def test_union_instance_value_is_rejected():
    inner = Inner(n=9)
    with pytest.raises(TypeError, match="v: expected dict, got Inner instance"):
        struct_of(StructOrInt).resolve({"v": inner})


# --------------------------------------------------------------------------
# Defaults may sit in any arm, and missing yields that default fresh
# --------------------------------------------------------------------------

@pytest.mark.parametrize("default", [0, "text", -99, "another"])
def test_int_str_union_default_variants(default):
    @dataclass
    class M:
        v: int | str = default

    assert struct_of(M).resolve({}) == {"v": default}


@pytest.mark.parametrize("value", [0, 1, 100, "a", "hello", None])
def test_three_way_union_accepts_and_returns_same(value):
    @dataclass
    class M:
        v: int | str | None = None

    assert struct_of(M).resolve({"v": value})["v"] == value


# --------------------------------------------------------------------------
# Enum members and instances travel by reference through a union
# --------------------------------------------------------------------------

def test_enum_member_by_reference_through_union():
    @dataclass
    class M:
        v: Role | None = None

    out = struct_of(M).resolve({"v": Role.ADMIN})
    assert out["v"] is Role.ADMIN


@pytest.mark.parametrize("member", [Role.ADMIN, Role.USER])
def test_each_enum_member_routes(member):
    @dataclass
    class M:
        v: Role | int = 0

    assert struct_of(M).resolve({"v": member})["v"] is member


# --------------------------------------------------------------------------
# Foreign types are rejected across many union shapes
# --------------------------------------------------------------------------

@pytest.mark.parametrize("foreign", [1.5, b"x", [], (), {}, 3j, object()])
def test_int_str_union_rejects_foreigns(foreign):
    @dataclass
    class M:
        v: int | str = 0

    with pytest.raises(TypeError):
        struct_of(M).resolve({"v": foreign})


@pytest.mark.parametrize("bad", [1.5, "x", b"y", []])
def test_optional_int_rejects_non_int_non_none(bad):
    @dataclass
    class M:
        v: int | None = None

    with pytest.raises(TypeError):
        struct_of(M).resolve({"v": bad})


# --------------------------------------------------------------------------
# Constraint on one arm never leaks to the other
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value,ok", [
    (0, True), (100, True), (-1, False), (101, False),
    ("", True), ("x" * 1000, True),
])
def test_constrained_int_arm_free_str_arm(value, ok):
    @dataclass
    class M:
        v: Annotated[int, Min(0), Max(100)] | str = 0

    if ok:
        assert struct_of(M).resolve({"v": value}) == {"v": value}
    else:
        with pytest.raises(ValueError):
            struct_of(M).resolve({"v": value})

from dataclasses import dataclass, field
from typing import Annotated

import pytest

from pytypehint.atoms import Min
from pytypehint.bridge import signature_of, struct_of


@dataclass
class Flat:
    a: int
    b: bool = False


def test_full_dict_passes_through():
    assert struct_of(Flat).resolve({"a": 1, "b": True}) == {"a": 1, "b": True}


def test_absent_with_default_is_filled():
    assert struct_of(Flat).resolve({"a": 1}) == {"a": 1, "b": False}


def test_absent_without_default_fails():
    with pytest.raises(TypeError, match=r"^missing key\(s\): a$"):
        struct_of(Flat).resolve({"b": True})


def test_extra_keys_fail_together():
    with pytest.raises(TypeError, match=r"^unexpected key\(s\): x, z$"):
        struct_of(Flat).resolve({"a": 1, "z": 1, "x": 1})


@pytest.mark.parametrize("key", [1, None, ("a",)])
def test_non_string_key_has_a_clear_error(key):
    with pytest.raises(
            TypeError,
            match=rf"^expected string keys, got {type(key).__name__}$"):
        struct_of(Flat).resolve({key: "a"})


@dataclass
class TwoRequired:
    a: int
    b: int
    c: int = 0


def test_missing_keys_fail_together_sorted():
    with pytest.raises(TypeError, match=r"^missing key\(s\): a, b$"):
        struct_of(TwoRequired).resolve({"c": 1})


def test_non_dict_input():
    with pytest.raises(TypeError, match="expected dict, got list"):
        struct_of(Flat).resolve([1, 2])


def test_input_is_not_mutated():
    data = {"a": 1}
    result = struct_of(Flat).resolve(data)
    assert data == {"a": 1}
    assert result == {"a": 1, "b": False}
    assert result is not data


@dataclass
class WithList:
    ns: list[int] = field(default_factory=lambda: [1, 2])


def test_default_list_is_a_fresh_list_each_call():
    s = struct_of(WithList)
    r1 = s.resolve({})
    r2 = s.resolve({})
    assert r1 == {"ns": [1, 2]}
    assert type(r1["ns"]) is list
    assert r1["ns"] is not r2["ns"]


def test_present_value_is_copied_as_is():
    mine = [3, 4]
    r = struct_of(WithList).resolve({"ns": mine})
    assert r["ns"] is mine


def test_resolve_lists_by_reference():
    data = {"ns": [1, 2, 3]}
    out = struct_of(WithList).resolve(data)
    assert out["ns"] is data["ns"]


def test_resolve_never_mutates_input():
    data = {"ns": [1, 2, 3]}
    before = dict(data)
    struct_of(WithList).resolve(data)
    assert data == before


def test_defaults_fresh_per_call():
    s = struct_of(WithList)
    r1 = s.resolve({})
    r2 = s.resolve({})
    assert r1["ns"] is not r2["ns"]


@dataclass
class Inner:
    a: int
    b: int = 5


@dataclass
class Outer:
    inner: Inner


def test_nested_dict_is_validated_but_not_filled():
    result = struct_of(Outer).resolve({"inner": {"a": 1}})
    assert result == {"inner": {"a": 1}}


def test_nested_dict_still_requires_its_mandatory_keys():
    with pytest.raises(TypeError, match=r"^inner: missing key\(s\): a$"):
        struct_of(Outer).resolve({"inner": {"b": 3}})


def test_nested_instance_is_rejected():
    inner = Inner(a=1, b=2)
    with pytest.raises(TypeError, match="inner: expected dict, got Inner instance"):
        struct_of(Outer).resolve({"inner": inner})


@dataclass
class Item:
    n: Annotated[int, Min(value=0)] = 0


@dataclass
class Bag:
    items: list[Item] = field(default_factory=list)


def test_chained_error_through_list_index():
    with pytest.raises(ValueError, match=r"^items: \[1\]: n: too small: -5"):
        struct_of(Bag).resolve({"items": [{"n": 0}, {"n": -5}]})


@dataclass
class A:
    x: int = 0


@dataclass
class B:
    y: int = 0


@dataclass
class Ambiguous:
    v: "A | B | None" = None


def test_ambiguous_union_dict_is_rejected():
    with pytest.raises(TypeError,
                       match=r'^v: ambiguous dict: field accepts A \| B — add "\$type" naming the variant$'):
        struct_of(Ambiguous).resolve({"v": {"x": 1}})


def test_signature_resolve_fills_and_returns():
    def fn(a: int, b: bool = False):
        ...

    assert signature_of(fn).resolve({"a": 1}) == {"a": 1, "b": False}


def test_signature_resolve_list_default_is_fresh():
    def fn(tags: list[int] = [1, 2]):
        ...

    sig = signature_of(fn)
    r1 = sig.resolve({})
    r2 = sig.resolve({})
    assert r1 == {"tags": [1, 2]}
    assert r1["tags"] is not r2["tags"]


def test_signature_resolve_missing_argument():
    def fn(a: int):
        ...

    with pytest.raises(TypeError, match=r"^missing argument\(s\): a$"):
        signature_of(fn).resolve({})


def test_signature_resolve_missing_arguments_fail_together():
    def fn(a: int, b: int, c: int = 0):
        ...

    with pytest.raises(TypeError, match=r"^missing argument\(s\): a, b$"):
        signature_of(fn).resolve({})


@dataclass
class Capped:
    # an impure factory: certifies at 0 (valid), then drifts out of range
    n: Annotated[int, Min(value=0)] = field(default_factory=lambda: next(_capped_seq))


_capped_seq = iter([0, -5])


def test_served_default_is_validated_at_runtime():
    # TAREA 2: the rematerialized portion is validated on each resolve, so an
    # impure recipe that drifts out of range fails here with a default segment.
    s = struct_of(Capped)                     # certifies: first serving is 0, valid
    with pytest.raises(ValueError, match=r"^n: default: too small: -5, minimum 0$"):
        s.resolve({})                         # second serving is -5, rejected


def test_signature_resolve_does_not_mutate_input():
    def fn(a: int, b: int = 0):
        ...

    data = {"a": 1}
    result = signature_of(fn).resolve(data)
    assert data == {"a": 1}
    assert result == {"a": 1, "b": 0}

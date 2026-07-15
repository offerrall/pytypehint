from dataclasses import dataclass, field

import pytest

from pytypehint import signature_of, struct_of


@pytest.mark.parametrize("n", range(1, 8))
def test_default_list_is_fresh_every_call(n):
    def fn(xs: list[int] = [1, 2, 3]):
        ...

    sig = signature_of(fn)
    results = [sig.resolve({}) for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            assert results[i]["xs"] is not results[j]["xs"]
            assert results[i]["xs"] == results[j]["xs"]


@pytest.mark.parametrize("payload", [[1], [1, 2], [1, 2, 3, 4, 5]])
def test_present_list_passes_by_reference(payload):
    @dataclass
    class M:
        xs: list[int] = field(default_factory=list)

    out = struct_of(M).resolve({"xs": payload})
    assert out["xs"] is payload


def test_default_never_shares_nested_containers():
    def fn(m: list[list[int]] = [[1], [2]]):
        ...

    sig = signature_of(fn)
    a = sig.resolve({})["m"]
    b = sig.resolve({})["m"]
    assert a is not b
    assert a[0] is not b[0]
    assert a == b == [[1], [2]]


@pytest.mark.parametrize("width", [1, 2, 5, 10, 25])
def test_default_list_width_is_fresh(width):
    literal = list(range(width))

    def fn(xs: list[int] = literal):
        ...

    sig = signature_of(fn)
    a = sig.resolve({})["xs"]
    b = sig.resolve({})["xs"]
    assert a is not b
    assert a == b == literal


@pytest.mark.parametrize("payload", [list(range(k)) for k in range(0, 10)])
def test_present_lists_of_varying_length_by_reference(payload):
    @dataclass
    class M:
        xs: list[int] = field(default_factory=list)

    assert struct_of(M).resolve({"xs": payload})["xs"] is payload


def test_nested_struct_list_default_is_fresh_and_instances_rematerialized():
    # 0.1.0: rematerialization (doctrine item 1) — a list default's items are
    # rematerialized recursively, so a dataclass instance inside is reconstructed
    # fresh per resolve, not shared. (Was: instances travel by reference, shared.)
    @dataclass
    class Item:
        n: int = 0

    shared = Item(n=5)

    def fn(items: list[Item] = [shared, shared]):
        ...

    sig = signature_of(fn)
    a = sig.resolve({})["items"]
    b = sig.resolve({})["items"]
    assert a is not b
    assert a[0] is not b[0]
    assert a[0] is not shared
    assert a[0] == b[0] == shared

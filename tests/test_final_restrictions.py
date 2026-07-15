from dataclasses import dataclass
from datetime import datetime, time, timezone
from enum import Enum, Flag
from pathlib import Path

import pytest

from pytypehint import EnumShape, signature_of, struct_of


DOCUMENTED_MESSAGES = (
    "page: expected dict, got Page instance",
    "unsupported type: <class 'complex'>",
    "list requires an item type: list[X]",
    "Field 'x': None must be accompanied by another option",
    "args: variadic parameters (*args/**kwargs) are not supported",
    "x: positional-only parameters are not supported",
    "x: missing type hint",
    "lambdas have no usable name; use a named function",
    "expected a plain function, got <bound method Service.run of service> — bound methods, partials and callable objects are not supported: wrap the call in a plain function (def run(q: str): return service.search(q))",
    "x: InitVar fields are not supported",
    "x: init=False fields are not supported",
    "field atoms cannot apply to list items",
    "unsupported type: <class 'datetime.datetime'>",
    "EnumShape.cls: Flag enums are not supported (OR-combinable, not a closed set)",
    "EnumShape.cls: enum has no members",
    "value: must be naive (no tzinfo): 12:00:00+00:00",
    "value: not finite: nan",
    "leaf: n: default: too large: 2, maximum 1",
    "self: looks like an unbound method — pytypehint takes plain functions; wrap the call (def run(q: str): return service.search(q))",
    "RecursionError: maximum recursion depth exceeded",
    'value: ambiguous dict: field accepts File | Url — add "$type" naming the variant',
    "value: $type: not a choice: 'Other', expected one of ('File', 'Url')",
    "value: $type: expected str, got int",
    "cart: items: [0]: size: default: too large: 145, maximum 100",
)


def test_documented_message_contract_is_pinned_character_for_character():
    root = Path(__file__).parents[1]
    docs = (root / "docs" / "restrictions.md").read_text(encoding="utf-8")
    docs += (root / "docs" / "build.md").read_text(encoding="utf-8")
    for message in DOCUMENTED_MESSAGES:
        assert message in docs


class Service:
    def __repr__(self):
        return "service"

    def run(self, q: str):
        pass


@dataclass
class _CycleNode:
    child: "_CycleNode | None" = None


def test_bound_method_rejection_message():
    with pytest.raises(TypeError) as info:
        signature_of(Service().run)
    assert str(info.value) == (
        "expected a plain function, got <bound method Service.run of service> — "
        "bound methods, partials and callable objects are not supported: wrap the "
        "call in a plain function (def run(q: str): return service.search(q))")


def test_unhinted_self_redirect_message():
    def run(self, q: str):
        pass

    with pytest.raises(TypeError) as info:
        signature_of(run)
    assert str(info.value) == (
        "self: looks like an unbound method — pytypehint takes plain functions; "
        "wrap the call (def run(q: str): return service.search(q))")


def test_cyclic_data_raises_raw_recursion_error():
    data = {}
    data["child"] = data
    with pytest.raises(RecursionError, match=r"^maximum recursion depth exceeded$"):
        struct_of(_CycleNode).build(data)


def test_closed_vocabulary_restriction_messages():
    @dataclass
    class Timestamp:
        value: datetime

    with pytest.raises(TypeError) as info:
        struct_of(Timestamp)
    assert str(info.value) == "unsupported type: <class 'datetime.datetime'>"

    class Bits(Flag):
        A = 1

    with pytest.raises(TypeError) as info:
        EnumShape(cls=Bits)
    assert str(info.value) == (
        "EnumShape.cls: Flag enums are not supported (OR-combinable, not a closed set)")

    class Empty(Enum):
        pass

    with pytest.raises(ValueError) as info:
        EnumShape(cls=Empty)
    assert str(info.value) == "EnumShape.cls: enum has no members"


def test_runtime_scalar_restriction_messages():
    @dataclass
    class Clock:
        value: time

    with pytest.raises(ValueError) as info:
        struct_of(Clock).build({"value": time(12, tzinfo=timezone.utc)})
    assert str(info.value) == "value: must be naive (no tzinfo): 12:00:00+00:00"

    @dataclass
    class Measurement:
        value: float

    with pytest.raises(ValueError) as info:
        struct_of(Measurement).build({"value": float("nan")})
    assert str(info.value) == "value: not finite: nan"

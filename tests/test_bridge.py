from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Annotated, Any, Optional

import pytest

from pytypehint.atoms import Max, Min
from pytypehint.bridge import struct_of
from pytypehint.shapes import Bool, Int, List, NoneShape
from pytypehint.structure import Field, Struct


@dataclass
class Deferred:
    n: int = 0
    active: bool = False
    maybe: int | None = None
    constrained: Annotated[int, Min(value=0), Max(value=10)] = 5
    ns: list[int] = field(default_factory=list)


def test_deferred_annotations_resolve():
    s = struct_of(Deferred)
    expected = Struct(cls=Deferred, fields=(
        Field(name="n", shape=(Int(),), default=0),
        Field(name="active", shape=(Bool(),), default=False),
        Field(name="maybe", shape=(Int(), NoneShape()), default=None),
        Field(name="constrained", shape=(Int(min=Min(value=0), max=Max(value=10)),), default=5),
        Field(name="ns", shape=(List(item=(Int(),)),), default=[]),
    ))
    assert repr(s.fields) == repr(expected.fields)


@dataclass
class DeferredNested:
    inner: Deferred = field(default_factory=Deferred)


def test_deferred_forward_reference_to_module_class():
    struct_of(DeferredNested)._check(DeferredNested())


@dataclass
class ExplicitString:
    n: "int" = 0
    maybe: "int | None" = None


def test_explicit_string_annotations():
    s = struct_of(ExplicitString)
    assert s.fields[0].shape == (Int(),)
    assert s.fields[1].shape == (Int(), NoneShape())


def test_unresolvable_forward_reference():
    @dataclass
    class C:
        x: "NoSuchType" = 0

    with pytest.raises(NameError):
        struct_of(C)


@dataclass
class Simple:
    n: int = 0


def named_function(n: int = 0) -> None:
    ...


class PlainClass:
    pass


class AnEnum(enum.Enum):
    A = 1


NOT_ACCEPTED = [
    int,
    str,
    list,
    PlainClass,
    AnEnum,
    5,
    "hola",
    None,
    [1, 2],
    {"n": 1},
    len,
    named_function,
    lambda x: x,
]


@pytest.mark.parametrize("obj", NOT_ACCEPTED, ids=range(len(NOT_ACCEPTED)))
def test_rejects_non_dataclass_types(obj):
    # 0.1.0: doctrine item 7 — a non-dataclass CLASS names itself and points at
    # @dataclass; non-class inputs keep the generic message.
    msg = "is not a dataclass — add @dataclass" if isinstance(obj, type) else "expected a dataclass type"
    with pytest.raises(TypeError, match=msg):
        struct_of(obj)


def test_instance_message_is_specific():
    with pytest.raises(TypeError, match="expected a dataclass type, got an instance of Simple"):
        struct_of(Simple())


def test_rejects_lambda():
    with pytest.raises(TypeError, match="expected a dataclass type"):
        struct_of(lambda x: x)


def test_functions_go_to_signature_of_now():
    with pytest.raises(TypeError, match="expected a dataclass type"):
        struct_of(named_function)


def test_method_is_a_function_for_inspect():
    class C:
        def m(self, n: int = 0) -> None:
            ...

    with pytest.raises(TypeError, match="expected a dataclass type"):
        struct_of(C.m)


class Color(enum.Enum):
    RED = 1


class NotADataclass:
    pass


def reject_bytes():
    @dataclass
    class C:
        b: bytes = b""

    return C


def reject_dict():
    @dataclass
    class C:
        d: dict[str, int] = field(default_factory=dict)

    return C


def reject_bare_dict():
    @dataclass
    class C:
        d: dict = field(default_factory=dict)

    return C


def reject_set():
    @dataclass
    class C:
        s: set[int] = field(default_factory=set)

    return C


def reject_tuple():
    @dataclass
    class C:
        t: tuple[int, int] = (0, 0)

    return C


def reject_any():
    @dataclass
    class C:
        x: Any = None

    return C


def reject_plain_class_field():
    @dataclass
    class C:
        x: NotADataclass = field(default_factory=NotADataclass)

    return C


UNSUPPORTED_TYPES = [
    reject_bytes,
    reject_dict,
    reject_bare_dict,
    reject_set,
    reject_tuple,
    reject_any,
    reject_plain_class_field,
]


@pytest.mark.parametrize("case", UNSUPPORTED_TYPES,
                         ids=lambda c: c.__name__.removeprefix("reject_"))
def test_unsupported_types(case):
    with pytest.raises(TypeError, match="unsupported type"):
        struct_of(case())


def test_unsupported_type_names_the_offender():
    @dataclass
    class C:
        b: bytes = b""

    with pytest.raises(TypeError, match=r"unsupported type: <class 'bytes'>"):
        struct_of(C)


def test_factory_is_called_at_compile_time():
    calls = []

    def factory():
        calls.append(1)
        return [len(calls)]

    @dataclass
    class C:
        ns: list[int] = field(default_factory=factory)

    assert calls == []
    s = struct_of(C)
    assert calls == [1]
    assert s.fields[0].default == [1]     # 0.1.0: certified product is a list, not a frozen tuple

    s2 = struct_of(C)
    assert calls == [1, 1]
    assert s2.fields[0].default == [2]


def test_materialized_default_is_frozen_and_isolated():
    @dataclass
    class C:
        ns: list[int] = field(default_factory=lambda: [1, 2])

    default = struct_of(C).fields[0].default
    assert default == [1, 2]              # 0.1.0: certified product is a list, not a frozen tuple
    assert type(default) is list

    assert C().ns == [1, 2]


def test_plain_default_is_not_copied():
    @dataclass
    class C:
        n: int = 7

    assert struct_of(C).fields[0].default == 7


def test_dataclass_with_no_fields():
    @dataclass
    class Empty:
        pass

    assert struct_of(Empty).fields == ()


def test_field_named_like_a_builtin():
    @dataclass
    class C:
        list: int = 0
        type: bool = False

    s = struct_of(C)
    assert [f.name for f in s.fields] == ["list", "type"]
    s._check(C())


def test_optional_alias_from_typing():
    @dataclass
    class C:
        n: Optional[int] = None

    (f,) = struct_of(C).fields
    assert f.shape == (Int(), NoneShape())

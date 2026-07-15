from dataclasses import dataclass, field
from typing import Annotated

import pytest

from pytypehint.atoms import Description, Label, Min
from pytypehint.bridge import struct_of
from pytypehint.shapes import Bool, List, NoneShape
from pytypehint.structure import Field, Struct
from pytypehint.utils import MISSING


def case_bare_bool():
    @dataclass
    class C:
        active: bool

    return C, Struct(cls=C, fields=(
        Field(name="active", shape=(Bool(),)),
    ))


def case_bool_with_default_true():
    @dataclass
    class C:
        active: bool = True

    return C, Struct(cls=C, fields=(
        Field(name="active", shape=(Bool(),), default=True),
    ))


def case_bool_with_default_false():
    @dataclass
    class C:
        active: bool = False

    return C, Struct(cls=C, fields=(
        Field(name="active", shape=(Bool(),), default=False),
    ))


def case_optional_bool():
    @dataclass
    class C:
        active: bool | None = None

    return C, Struct(cls=C, fields=(
        Field(name="active", shape=(Bool(), NoneShape()), default=None),
    ))


def case_bool_with_label():
    @dataclass
    class C:
        active: Annotated[bool, Label(value="Active")]

    return C, Struct(cls=C, fields=(
        Field(name="active", shape=(Bool(),), label=Label(value="Active")),
    ))


def case_bool_with_label_and_description():
    @dataclass
    class C:
        active: Annotated[bool, Label(value="Active"), Description(value="Enable feature")] = False

    return C, Struct(cls=C, fields=(
        Field(
            name="active",
            shape=(Bool(),),
            default=False,
            label=Label(value="Active"),
            description=Description(value="Enable feature"),
        ),
    ))


def case_optional_bool_with_label():
    @dataclass
    class C:
        active: Annotated[bool | None, Label(value="Active")] = None

    return C, Struct(cls=C, fields=(
        Field(
            name="active",
            shape=(Bool(), NoneShape()),
            default=None,
            label=Label(value="Active"),
        ),
    ))


def case_list_of_bool():
    @dataclass
    class C:
        flags: list[bool] = field(default_factory=list)

    return C, Struct(cls=C, fields=(
        Field(name="flags", shape=(List(item=(Bool(),)),), default=[]),
    ))


def case_list_of_bool_with_factory_values():
    @dataclass
    class C:
        flags: list[bool] = field(default_factory=lambda: [True, False])

    return C, Struct(cls=C, fields=(
        Field(name="flags", shape=(List(item=(Bool(),)),), default=[True, False]),
    ))


def case_nested_dataclass_with_bool():
    @dataclass
    class Inner:
        on: bool = True

    @dataclass
    class Outer:
        inner: Inner = field(default_factory=Inner)

    return Outer, Struct(cls=Outer, fields=(
        Field(
            name="inner",
            shape=(Struct(cls=Inner, fields=(
                Field(name="on", shape=(Bool(),), default=True),
            )),),
            default=Inner(),
        ),
    ))


def case_multiple_bool_fields():
    @dataclass
    class C:
        a: bool
        b: bool = True
        c: bool | None = None

    return C, Struct(cls=C, fields=(
        Field(name="a", shape=(Bool(),)),
        Field(name="b", shape=(Bool(),), default=True),
        Field(name="c", shape=(Bool(), NoneShape()), default=None),
    ))


SCHEMA_CASES = [
    case_bare_bool,
    case_bool_with_default_true,
    case_bool_with_default_false,
    case_optional_bool,
    case_bool_with_label,
    case_bool_with_label_and_description,
    case_optional_bool_with_label,
    case_list_of_bool,
    case_list_of_bool_with_factory_values,
    case_nested_dataclass_with_bool,
    case_multiple_bool_fields,
]


@pytest.mark.parametrize("case", SCHEMA_CASES, ids=lambda c: c.__name__.removeprefix("case_"))
def test_schema(case):
    cls, expected = case()
    assert repr(struct_of(cls).fields) == repr(expected.fields)


def reject_bool_with_type_metadata():
    @dataclass
    class C:
        active: Annotated[bool, Min(value=1)]

    return C


def reject_bool_with_int_default():
    @dataclass
    class C:
        active: bool = 1

    return C


REJECT_CASES = [
    (reject_bool_with_type_metadata, TypeError, "unsupported metadata for bool"),
    (reject_bool_with_int_default, TypeError, "expected bool"),
]


@pytest.mark.parametrize("case, exc, match", REJECT_CASES,
                         ids=lambda v: v.__name__.removeprefix("reject_") if callable(v) else "")
def test_schema_rejected(case, exc, match):
    with pytest.raises(exc, match=match):
        struct_of(case())

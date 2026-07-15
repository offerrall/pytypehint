from dataclasses import dataclass, make_dataclass
from datetime import date, time
from enum import Enum
from typing import Annotated, TypeAlias

import pytest

from pytypehint import Extra, signature_of, struct_of
from pytypehint.shapes import Bool, Date, Float, Int, List, NoneShape, Str, Time


def test_extra_construction_equality_and_hash():
    assert Extra("x") == Extra(value="x")
    assert Extra("x") != Extra("y")
    assert hash(Extra("x")) == hash(Extra("x"))

    with pytest.raises(ValueError, match=r"^Extra\.value must not be empty$"):
        Extra("")
    with pytest.raises(TypeError, match=r"^Extra\.value must be str, got int$"):
        Extra(3)


@pytest.mark.parametrize("hint, shape_type", [
    (Annotated[int, Extra("hint")], Int),
    (Annotated[float, Extra("hint")], Float),
    (Annotated[str, Extra("hint")], Str),
    (Annotated[bool, Extra("hint")], Bool),
    (Annotated[date, Extra("hint")], Date),
    (Annotated[time, Extra("hint")], Time),
    (int | Annotated[None, Extra("hint")], NoneShape),
    (Annotated[list[int], Extra("hint")], List),
])
def test_extra_compiles_on_every_vocabulary_shape(hint, shape_type):
    model = make_dataclass("Model", [("value", hint)])
    shape = next(shape for shape in struct_of(model).fields[0].shape
                 if type(shape) is shape_type)

    assert type(shape) is shape_type
    assert shape.extra == Extra("hint")


def test_extra_does_not_change_validation_or_default_certification():
    @dataclass
    class Plain:
        value: int = 3

    @dataclass
    class WithExtra:
        value: Annotated[int, Extra("hint")] = 3

    plain = struct_of(Plain)
    annotated = struct_of(WithExtra)
    assert plain.resolve({"value": 4}) == annotated.resolve({"value": 4})
    assert annotated.resolve({}) == {"value": 3}

    for schema in (plain, annotated):
        with pytest.raises(TypeError, match=r"value: expected int, got str"):
            schema.resolve({"value": "4"})

    @dataclass
    class BadDefault:
        value: Annotated[int, Extra("hint")] = "3"

    with pytest.raises(
            TypeError,
            match=r"Field 'value': default expected int, got str"):
        struct_of(BadDefault)


def test_extra_applies_to_a_list_item_shape():
    @dataclass
    class Model:
        values: list[Annotated[str, Extra("a")]]

    shape = struct_of(Model).fields[0].shape[0]
    assert type(shape) is List
    assert shape.item[0].extra == Extra("a")


def test_extra_layering_outer_and_rightmost_win():
    Inner: TypeAlias = Annotated[int, Extra("a")]

    @dataclass
    class Model:
        outer: Annotated[Inner, Extra("b")]
        same: Annotated[int, Extra("a"), Extra("b")]

    outer, same = struct_of(Model).fields
    assert outer.shape[0].extra == Extra("b")
    assert same.shape[0].extra == Extra("b")


def test_extra_is_rejected_on_enum_and_dataclass_metadata():
    class Kind(Enum):
        A = "a"

    @dataclass
    class Nested:
        value: int

    enum_model = make_dataclass(
        "EnumModel", [("value", Annotated[Kind, Extra("x")])])
    struct_model = make_dataclass(
        "StructModel", [("value", Annotated[Nested, Extra("x")])])

    with pytest.raises(
            TypeError,
            match=r"unsupported metadata for enum: Extra\(value='x'\)"):
        struct_of(enum_model)
    with pytest.raises(
            TypeError,
            match=r"unsupported metadata for dataclass: Extra\(value='x'\)"):
        struct_of(struct_model)


def test_extra_on_a_multi_type_union_requires_per_option_metadata():
    @dataclass
    class Model:
        value: Annotated[int | str, Extra("x")]

    with pytest.raises(
            TypeError,
            match=r"value: metadata on a union of multiple types must go per option"):
        struct_of(Model)


def test_extra_round_trips_through_struct_and_signature_compilation():
    @dataclass
    class Model:
        value: Annotated[str, Extra("struct")]

    def run(value: Annotated[int, Extra("signature")]):
        pass

    assert struct_of(Model).fields[0].shape[0].extra == Extra("struct")
    assert signature_of(run).params[0].shape[0].extra == Extra("signature")

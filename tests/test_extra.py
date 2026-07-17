from dataclasses import dataclass, make_dataclass
from datetime import date, time
from enum import Enum
from typing import Annotated, TypeAlias

import pytest

from pytypehint import Extra, signature_of, struct_of
from pytypehint.shapes import Bool, Date, Float, Int, List, NoneShape, Str, Time


def test_extra_construction_equality_and_hash():
    assert Extra("pkg.k", "x") == Extra(key="pkg.k", value="x")
    assert Extra("pkg.k", "x") != Extra("pkg.k", "y")
    assert Extra("pkg.k", "x") != Extra("other.k", "x")
    assert hash(Extra("pkg.k", "x")) == hash(Extra("pkg.k", "x"))


def test_extra_key_must_be_a_non_empty_namespaced_str():
    with pytest.raises(TypeError, match=r"^Extra\.key must be str, got int$"):
        Extra(3, "x")
    with pytest.raises(ValueError, match=r"^Extra\.key must not be empty$"):
        Extra("", "x")
    with pytest.raises(
            ValueError,
            match=r"^Extra\.key must be namespaced \('package\.name'\), got 'color'$"):
        Extra("color", "x")


def test_extra_value_must_be_str_and_may_be_empty():
    with pytest.raises(TypeError, match=r"^Extra\.value must be str, got int$"):
        Extra("pkg.k", 3)

    # The core stores the value and never reads it; emptiness is the wrapper's business.
    assert Extra("pkg.k", "").value == ""


def test_extras_are_readable_as_a_dict():
    @dataclass
    class Model:
        value: Annotated[int, Extra("ledform.color", "red")]

    shape = struct_of(Model).fields[0].shape[0]
    assert shape.extras == {"ledform.color": "red"}


def test_an_empty_value_survives_compilation():
    @dataclass
    class Model:
        value: Annotated[int, Extra("ledform.color", "")]

    assert struct_of(Model).fields[0].shape[0].extras == {"ledform.color": ""}


def test_extras_property_is_a_fresh_dict_each_access():
    @dataclass
    class Model:
        value: Annotated[int, Extra("ledform.color", "red")]

    shape = struct_of(Model).fields[0].shape[0]
    shape.extras["ledform.color"] = "blue"

    assert shape.extras == {"ledform.color": "red"}


def test_different_keys_merge_and_writing_order_does_not_change_the_shape():
    @dataclass
    class Model:
        one: Annotated[int, Extra("a.x", "1"), Extra("b.y", "2")]
        other: Annotated[int, Extra("b.y", "2"), Extra("a.x", "1")]

    one, other = struct_of(Model).fields

    assert one.shape[0].extras == {"a.x": "1", "b.y": "2"}
    # Sorted storage: equality answers about the pairs, not about the typing.
    assert one.shape[0] == other.shape[0]
    assert hash(one.shape[0]) == hash(other.shape[0])


def test_shapes_with_extras_are_hashable_and_compare_by_pairs():
    @dataclass
    class Model:
        red: Annotated[int, Extra("a.x", "red")]
        same: Annotated[int, Extra("a.x", "red")]
        blue: Annotated[int, Extra("a.x", "blue")]
        elsewhere: Annotated[int, Extra("b.x", "red")]
        bare: int

    red, same, blue, elsewhere, bare = (f.shape[0] for f in struct_of(Model).fields)

    assert red == same
    assert len({red, same}) == 1
    assert red != blue
    assert red != elsewhere
    assert red != bare


def test_a_repeated_key_layers_rightmost_and_outermost_first():
    Inner: TypeAlias = Annotated[int, Extra("a.x", "inner")]

    @dataclass
    class Model:
        # Typing flattens Annotated, so the outer layer is the rightmost atom:
        # both fields are one hint and one rule.
        outer: Annotated[Inner, Extra("a.x", "outer")]
        same: Annotated[int, Extra("a.x", "left"), Extra("a.x", "right")]
        # Layering is per key: an override leaves the other keys standing.
        kept: Annotated[Inner, Extra("a.x", "outer"), Extra("b.y", "kept")]

    outer, same, kept = struct_of(Model).fields

    assert outer.shape[0].extras == {"a.x": "outer"}
    assert same.shape[0].extras == {"a.x": "right"}
    assert kept.shape[0].extras == {"a.x": "outer", "b.y": "kept"}


@pytest.mark.parametrize("hint, shape_type", [
    (Annotated[int, Extra("pkg.k", "hint")], Int),
    (Annotated[float, Extra("pkg.k", "hint")], Float),
    (Annotated[str, Extra("pkg.k", "hint")], Str),
    (Annotated[bool, Extra("pkg.k", "hint")], Bool),
    (Annotated[date, Extra("pkg.k", "hint")], Date),
    (Annotated[time, Extra("pkg.k", "hint")], Time),
    (int | Annotated[None, Extra("pkg.k", "hint")], NoneShape),
    (Annotated[list[int], Extra("pkg.k", "hint")], List),
])
def test_extras_compile_on_every_vocabulary_shape(hint, shape_type):
    model = make_dataclass("Model", [("value", hint)])
    shape = next(shape for shape in struct_of(model).fields[0].shape
                 if type(shape) is shape_type)

    assert type(shape) is shape_type
    assert shape.extras == {"pkg.k": "hint"}


def test_extras_do_not_change_validation_or_default_certification():
    @dataclass
    class Plain:
        value: int = 3

    @dataclass
    class WithExtra:
        value: Annotated[int, Extra("pkg.k", "hint")] = 3

    plain = struct_of(Plain)
    annotated = struct_of(WithExtra)
    assert plain.resolve({"value": 4}) == annotated.resolve({"value": 4})
    assert annotated.resolve({}) == {"value": 3}

    for schema in (plain, annotated):
        with pytest.raises(TypeError, match=r"value: expected int, got str"):
            schema.resolve({"value": "4"})

    @dataclass
    class BadDefault:
        value: Annotated[int, Extra("pkg.k", "hint")] = "3"

    with pytest.raises(
            TypeError,
            match=r"Field 'value': default expected int, got str"):
        struct_of(BadDefault)


def test_extras_apply_to_a_list_item_shape():
    @dataclass
    class Model:
        values: list[Annotated[str, Extra("a.x", "1")]]

    shape = struct_of(Model).fields[0].shape[0]
    assert type(shape) is List
    assert shape.item[0].extras == {"a.x": "1"}


def test_extra_is_rejected_on_enum_and_dataclass_metadata():
    class Kind(Enum):
        A = "a"

    @dataclass
    class Nested:
        value: int

    enum_model = make_dataclass(
        "EnumModel", [("value", Annotated[Kind, Extra("a.x", "1")])])
    struct_model = make_dataclass(
        "StructModel", [("value", Annotated[Nested, Extra("a.x", "1")])])

    with pytest.raises(
            TypeError,
            match=r"unsupported metadata for enum: Extra\(key='a\.x', value='1'\)"):
        struct_of(enum_model)
    with pytest.raises(
            TypeError,
            match=r"unsupported metadata for dataclass: Extra\(key='a\.x', value='1'\)"):
        struct_of(struct_model)


def test_an_unknown_atom_is_still_unsupported_metadata_next_to_extras():
    """Merging extras must not turn a typo into metadata the compiler waves through."""
    @dataclass(frozen=True)
    class Colour:
        value: str

    model = make_dataclass(
        "Model", [("value", Annotated[int, Extra("a.x", "1"), Colour("red")])])

    with pytest.raises(TypeError) as error:
        struct_of(model)

    assert str(error.value) == f"unsupported metadata for int: {Colour('red')!r}"


def test_extra_on_a_multi_type_union_requires_per_option_metadata():
    @dataclass
    class Model:
        value: Annotated[int | str, Extra("a.x", "1")]

    with pytest.raises(
            TypeError,
            match=r"value: metadata on a union of multiple types must go per option"):
        struct_of(Model)


def test_extras_round_trip_through_struct_and_signature_compilation():
    @dataclass
    class Model:
        value: Annotated[str, Extra("a.x", "struct")]

    def run(value: Annotated[int, Extra("a.x", "signature")]):
        pass

    assert struct_of(Model).fields[0].shape[0].extras == {"a.x": "struct"}
    assert signature_of(run).params[0].shape[0].extras == {"a.x": "signature"}


def test_two_wrapper_namespaces_coexist_on_one_field():
    """Two packages annotate the same field; each reads its own keys by prefix."""
    @dataclass
    class Model:
        volume: Annotated[
            int,
            Extra("a.x", "left"),
            Extra("a.style", "bold"),
            Extra("b.x", "right"),
        ]

    extras = struct_of(Model).fields[0].shape[0].extras
    assert extras == {"a.x": "left", "a.style": "bold", "b.x": "right"}

    # Filtering is the wrapper's job, one dict comprehension away.
    a = {k.removeprefix("a."): v for k, v in extras.items() if k.startswith("a.")}
    b = {k.removeprefix("b."): v for k, v in extras.items() if k.startswith("b.")}

    assert a == {"x": "left", "style": "bold"}
    assert b == {"x": "right"}


def test_hand_built_shapes_reject_a_broken_extras_mapping():
    with pytest.raises(TypeError, match=r"^Int\._extras must be tuple, got dict$"):
        Int(_extras={"a.x": "1"})
    with pytest.raises(
            TypeError,
            match=r"^Int\._extras: expected a \(key, value\) pair of str, got 'a\.x'$"):
        Int(_extras=("a.x",))
    with pytest.raises(ValueError, match=r"^Int\._extras must not repeat keys$"):
        Int(_extras=(("a.x", "1"), ("a.x", "2")))


def test_hand_built_extras_are_stored_sorted():
    assert Int(_extras=(("b.y", "2"), ("a.x", "1")))._extras == (("a.x", "1"), ("b.y", "2"))

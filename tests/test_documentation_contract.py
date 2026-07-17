"""Executable contract for README.md and docs/*.md.

The documentation deliberately repeats its central promises.  This module
groups equivalent claims into one test and names the source documents in each
section so that prose and behaviour cannot silently drift apart.
"""

from dataclasses import InitVar, dataclass, field, make_dataclass
from datetime import date, datetime, time, timezone
from enum import Enum, Flag
from typing import Annotated, Literal

import pytest

import pytypehint
from pytypehint import (
    Choices, Description, Extra, Field, Int, Label, Max, Min, MultipleOf,
    OptionalToggle, Pattern, SchemaTypeError, SchemaValueError, Signature,
    Slider, Struct, signature_of, struct_of,
)
from pytypehint.shapes import (
    Bool, Date, EnumShape, Float, List, NoneShape, Str, Time,
)


# README example; README "Guarantees"; docs/build.md.
@dataclass(frozen=True)
class _Page:
    number: Annotated[int, Min(1)] = 1
    size: Annotated[int, Min(1), Max(100), Label("Page size")] = 20


@dataclass
class _Search:
    query: str
    page: _Page = _Page()
    tags: list[str] = field(default_factory=list)


def test_readme_example_is_executable_and_reports_the_documented_error():
    schema = struct_of(_Search)
    assert schema.build({"query": "python", "page": {"size": 50}}) == _Search(
        query="python", page=_Page(number=1, size=50), tags=[])

    with pytest.raises(ValueError) as error:
        schema.build({"query": "python", "page": {"size": 500}})
    assert str(error.value) == "page: size: too large: 500, maximum 100"


# README "Public API".
def test_every_documented_public_name_is_exported_from_the_package():
    documented = {
        "struct_of", "signature_of", "Struct", "Field", "Signature",
        "SchemaTypeError", "SchemaValueError", "Shape", "Int", "Float",
        "Str", "Bool", "Date", "Time", "List", "NoneShape", "EnumShape",
        "Min", "Max", "Choices", "MultipleOf", "Pattern", "IsPathFile",
        "Label", "Description", "Placeholder", "Step", "Slider",
        "IsPassword", "Rows", "Extra", "OptionalToggle", "MISSING",
    }
    assert documented <= set(pytypehint.__all__)
    assert all(hasattr(pytypehint, name) for name in documented)


# README "Vocabulary"; docs/vocabulary.md; docs/philosophy.md "Hints are exact".
@pytest.mark.parametrize("shape, good, bad", [
    (Int(), 1, True),
    (Float(), 1.0, 1),
    (Str(), "1", 1),
    (Bool(), True, 1),
    (Date(), date(2024, 1, 1), datetime(2024, 1, 1)),
    (Time(), time(12, 0), "12:00"),
    (NoneShape(), None, 0),
])
def test_documented_scalar_vocabulary_uses_exact_types(shape, good, bad):
    shape._check(good)
    with pytest.raises(TypeError):
        shape._check(bad)


def test_time_is_naive_and_floats_are_finite():
    with pytest.raises(ValueError, match=r"must be naive"):
        Time()._check(time(12, tzinfo=timezone.utc))
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match=r"not finite"):
            Float()._check(value)


class _Role(Enum):
    ADMIN = "admin"


class _OtherRole(Enum):
    ADMIN = "admin"


def test_enum_input_must_be_a_member_of_the_exact_enum():
    shape = EnumShape(cls=_Role)
    shape._check(_Role.ADMIN)
    for wrong in ("admin", _OtherRole.ADMIN):
        with pytest.raises(TypeError):
            shape._check(wrong)


# docs/vocabulary.md list, nesting, union, None-item and Literal claims.
@dataclass
class _Collections:
    matrix: list[list[int]]
    holes: list[int | None]
    mode: Literal["fast", "safe"]


def test_nested_lists_none_items_and_literals_match_the_vocabulary_table():
    schema = struct_of(_Collections)
    assert schema.resolve({
        "matrix": [[1], [2, 3]], "holes": [1, None, 2], "mode": "fast",
    }) == {"matrix": [[1], [2, 3]], "holes": [1, None, 2], "mode": "fast"}

    with pytest.raises(TypeError, match=r"matrix: \[0\]: \[1\]: expected int"):
        schema.resolve({"matrix": [[1, "2"]], "holes": [], "mode": "fast"})
    with pytest.raises(ValueError, match=r"mode: not a choice"):
        schema.resolve({"matrix": [], "holes": [], "mode": "FAST"})


# docs/atoms.md accepted semantics and compile-time cross-checks.
def test_limit_atoms_validate_and_notation_atoms_only_describe():
    @dataclass
    class Model:
        value: Annotated[
            int, Min(0), Max(10), MultipleOf(2), Label("Value"),
            Description("Even"), Extra("widget.kind", "dial"),
        ]

    compiled = struct_of(Model)
    fld = compiled.fields[0]
    assert fld.label == Label("Value")
    assert fld.description == Description("Even")
    assert fld.shape[0].extras == {"widget.kind": "dial"}
    assert compiled.resolve({"value": 4}) == {"value": 4}
    with pytest.raises(ValueError, match=r"not a multiple"):
        compiled.resolve({"value": 3})


@pytest.mark.parametrize("hint, message", [
    (Annotated[int, Min(2), Max(1)], "empty range"),
    (Annotated[int, Min(0), Choices(values=(-1,))], "below minimum"),
    (Annotated[int, Slider()], "slider requires min and max"),
    (Annotated[int, OptionalToggle(True)], r"requires an optional field"),
])
def test_documented_atom_contradictions_fail_at_compilation(hint, message):
    model = make_dataclass("DocumentedContradiction", [("value", hint)])
    with pytest.raises((TypeError, ValueError), match=message):
        struct_of(model)


def test_pattern_uses_fullmatch_and_custom_message():
    shape = Str(pattern=Pattern(r"\d+", message="digits only"))
    shape._check("123")
    with pytest.raises(ValueError, match=r"^digits only$"):
        shape._check("123x")


def test_atom_layering_uses_outer_or_rightmost_value():
    Percent = Annotated[int, Min(0), Max(100)]
    Narrow = Annotated[Percent, Max(50)]
    Optional = Annotated[int | None, OptionalToggle(True)]
    Closed = Annotated[Optional, OptionalToggle(False)]

    model = make_dataclass("Layered", [("n", Narrow), ("optional", Closed)])
    n, optional = struct_of(model).fields
    assert n.shape[0].max == Max(50)
    assert optional.optional_toggle == OptionalToggle(False)


def test_extra_layering_and_read_only_snapshot_match_atoms_documentation():
    Themed = Annotated[
        int, Extra("ledform.color", "red"), Extra("ledform.rows", "2")]
    Blue = Annotated[Themed, Extra("ledform.color", "blue")]
    model = make_dataclass("ThemedModel", [("value", Blue)])
    shape = struct_of(model).fields[0].shape[0]

    assert shape.extras == {"ledform.color": "blue", "ledform.rows": "2"}
    snapshot = shape.extras
    snapshot.clear()
    assert shape.extras == {"ledform.color": "blue", "ledform.rows": "2"}


# docs/build.md and docs/resolve.md.
@dataclass
class _File:
    path: str


@dataclass
class _Url:
    value: str


@dataclass
class _Source:
    value: _File | _Url


def test_resolve_preserves_and_build_consumes_dataclass_union_discriminator():
    data = {"value": {"$type": "_Url", "value": "https://example.test"}}
    schema = struct_of(_Source)
    assert schema.resolve(data) == data
    assert schema.build(data) == _Source(value=_Url("https://example.test"))


@pytest.mark.parametrize("payload, message", [
    ({"value": {"value": "x"}}, r"ambiguous dict"),
    ({"value": {"$type": "Other", "value": "x"}}, r"\$type: not a choice"),
    ({"value": {"$type": 1, "value": "x"}}, r"\$type: expected str"),
])
def test_documented_discriminator_failures(payload, message):
    with pytest.raises((TypeError, ValueError), match=message):
        struct_of(_Source).build(payload)


def test_signature_build_constructs_kwargs_without_calling_the_function():
    calls = []

    def run(page: _Page = _Page()):
        calls.append(page)

    kwargs = signature_of(run).build({"page": {"size": 50}})
    assert kwargs == {"page": _Page(size=50)}
    assert calls == []


def test_resolve_keeps_nested_dicts_while_build_constructs_instances():
    resolved = struct_of(_Search).resolve({"query": "x", "page": {"size": 30}})
    built = struct_of(_Search).build({"query": "x", "page": {"size": 30}})
    # resolve validates the supplied nested dictionary as-is; build crosses the
    # construction boundary and serves the nested dataclass's missing default.
    assert resolved["page"] == {"size": 30}
    assert type(resolved["page"]) is dict
    assert built.page == _Page(number=1, size=30)


def test_input_dataclass_instances_are_rejected_by_resolve_and_build():
    schema = struct_of(_Search)
    data = {"query": "x", "page": _Page()}
    for operation in (schema.resolve, schema.build):
        with pytest.raises(TypeError, match=r"page: expected dict, got _Page instance"):
            operation(data)


# docs/defaults.md and docs/philosophy.md "Defaults are recipes".
def test_default_factory_is_certified_once_and_run_once_per_missing_serving():
    calls = []

    def recipe():
        calls.append(len(calls))
        return [1]

    model = make_dataclass(
        "RecipeModel", [("values", list[int], field(default_factory=recipe))])
    schema = struct_of(model)
    assert len(calls) == 1

    first = schema.resolve({})["values"]
    second = schema.build({}).values
    assert len(calls) == 3
    assert first == second == [1]
    assert first is not second

    assert schema.resolve({"values": [2]}) == {"values": [2]}
    assert len(calls) == 3


def test_impure_default_is_revalidated_with_a_default_path_segment():
    values = iter((1, 2))
    model = make_dataclass(
        "Impure", [("n", Annotated[int, Max(1)], field(default_factory=lambda: next(values)))])
    schema = struct_of(model)
    with pytest.raises(ValueError) as error:
        schema.resolve({})
    assert error.value.path == ("n", "default")
    assert error.value.leaf == "too large: 2, maximum 1"


# README guarantees; docs/philosophy.md identity and fail-fast claims.
def test_struct_field_and_signature_use_identity_equality():
    def fn(value: int):
        pass

    assert struct_of(_Search) != struct_of(_Search)
    assert Field(name="x", shape=(Int(),)) != Field(name="x", shape=(Int(),))
    assert signature_of(fn) != signature_of(fn)
    assert isinstance(struct_of(_Search), Struct)
    assert isinstance(signature_of(fn), Signature)


def test_schema_errors_preserve_path_leaf_and_builtin_error_subclass():
    @dataclass
    class Model:
        values: list[Annotated[int, Max(1)]]

    with pytest.raises(SchemaValueError) as value_error:
        struct_of(Model).resolve({"values": [0, 2]})
    assert value_error.value.path == ("values", 1)
    assert value_error.value.leaf == "too large: 2, maximum 1"
    assert isinstance(value_error.value, ValueError)

    with pytest.raises(SchemaTypeError) as type_error:
        struct_of(Model).resolve({"values": ["0"]})
    assert type_error.value.path == ("values", 0)
    assert type_error.value.leaf == "expected int, got str"
    assert isinstance(type_error.value, TypeError)


# docs/restrictions.md: closed vocabulary and structural restrictions.
@pytest.mark.parametrize("hint, message", [
    (complex, r"unsupported type: <class 'complex'>"),
    (list, r"list requires an item type: list\[X\]"),
    (None, r"None must be accompanied by another option"),
    (datetime, r"unsupported type: <class 'datetime.datetime'>"),
])
def test_documented_unsupported_field_hints_fail_with_useful_messages(hint, message):
    model = make_dataclass("Unsupported", [("x", hint)])
    with pytest.raises((TypeError, ValueError), match=message):
        struct_of(model)


def test_signature_restrictions_cover_variadics_positional_only_missing_hints_and_lambda():
    def variadic(*args: int):
        pass

    def positional(x: int, /):
        pass

    def missing(x):
        pass

    cases = [
        (variadic, r"args: variadic parameters"),
        (positional, r"x: positional-only parameters"),
        (missing, r"x: missing type hint"),
        (lambda x: x, r"lambdas have no usable name"),
    ]
    for fn, message in cases:
        with pytest.raises(TypeError, match=message):
            signature_of(fn)


def test_dataclass_initvar_and_init_false_are_rejected():
    @dataclass
    class WithInitVar:
        value: InitVar[int]

    @dataclass
    class WithInitFalse:
        value: int = field(init=False, default=1)

    with pytest.raises(TypeError, match=r"value: InitVar fields are not supported"):
        struct_of(WithInitVar)
    with pytest.raises(TypeError, match=r"value: init=False fields are not supported"):
        struct_of(WithInitFalse)


class _Flags(Flag):
    A = 1
    B = 2


class _EmptyEnum(Enum):
    pass


def test_flag_and_empty_enums_are_rejected_as_documented():
    with pytest.raises(TypeError, match=r"Flag enums are not supported"):
        EnumShape(cls=_Flags)
    with pytest.raises(ValueError, match=r"enum has no members"):
        EnumShape(cls=_EmptyEnum)


def test_extra_restrictions_match_the_documented_messages():
    with pytest.raises(ValueError, match=r"must be namespaced"):
        Extra("color", "red")
    with pytest.raises(ValueError, match=r"must not be empty"):
        Extra("", "red")
    with pytest.raises(TypeError, match=r"Extra\.key must be str"):
        Extra(1, "red")
    with pytest.raises(TypeError, match=r"Extra\.value must be str"):
        Extra("pkg.color", 1)

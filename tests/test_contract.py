"""Executable contract for docs/contract.md — the portable document.

`Struct.to_dict()` and `Signature.to_dict()` write "a portable tree — dicts,
lists, strings, numbers, booleans and null, and nothing else".  This module
freezes the *document*, not the emitter: every claim below is quoted from
docs/contract.md, and the tests are written against the prose rather than
against `pytypehint.contract`.

The coverage here is by shape and by atom, plus the three properties the format
rests on: every value is JSON, nothing of the implementation leaks through, and
absence, `null` and `false` stay three distinguishable things.  References,
recursion, sharing, ids of homonym definitions and the portable spelling of
defaults have their own module.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, make_dataclass
from datetime import date, time
from enum import Enum
from typing import Annotated

import pytest

from pytypehint import (
    MISSING, Choices, Description, Extra, FileHint, IsPassword, Label, Max,
    Min, MultipleOf, OptionalToggle, Pattern, Placeholder, Rows, Slider, Step,
    signature_of, struct_of,
)


# ---------------------------------------------------------------------------
# Subjects
# ---------------------------------------------------------------------------

class _Role(Enum):
    ADMIN = "admin"
    USER = "user"


@dataclass
class _Inner:
    x: int = 1


@dataclass
class _User:
    """docs/contract.md's opening example, verbatim."""
    name: str
    birthday: date


@dataclass
class _Everything:
    """One field per shape, carrying every atom its shape admits."""
    number: Annotated[int, Min(0, exclusive=True), Max(15, exclusive=True),
                      MultipleOf(5), Choices(values=(5, 10)), Step(5), Slider(),
                      Placeholder("p"), Extra("b.key", "2"), Extra("a.key", "1")]
    ratio: Annotated[float, Min(0.0, exclusive=True), Max(1.0, exclusive=True),
                     Choices(values=(0.5,)), Step(0.01),
                     Slider(show_value=False), Placeholder("p")]
    word: Annotated[str, Min(2), Max(20), Pattern("[a-z]+", message="lowercase"),
                    Choices(values=("ab", "cd")), IsPassword(), Rows(5),
                    Placeholder("p")]
    report: Annotated[str, FileHint(extensions=(".pdf",), min_size=0,
                                    max_size=1048576)]
    anything: Annotated[str, FileHint()]
    flag: Annotated[bool, Extra("a.key", "1")]
    day: Annotated[date, Min(date(2024, 1, 1), exclusive=True),
                   Max(date(2024, 12, 31), exclusive=True),
                   Choices(values=(date(2024, 6, 1),)), Placeholder("p")]
    hour: Annotated[time, Min(time(9, 0), exclusive=True),
                    Max(time(18, 0), exclusive=True),
                    Choices(values=(time(10, 0),)), Placeholder("p")]
    tags: Annotated[list[str], Min(0), Max(10), Extra("a.key", "1")]
    role: _Role
    inner: _Inner
    described: Annotated[str, Label("Described"), Description("A description.")]
    maybe: Annotated[int | None, OptionalToggle(False)] = None


@dataclass
class _Unions:
    """Slots holding two or more options, where `id` is written."""
    number_or_ratio: int | float
    text_or_day: str | date
    tags: list[str] | None = None
    holes: list[int | None] | None = None
    matrix: list[list[str]] | None = None
    role: _Role | None = None
    inner: _Inner | None = None


@dataclass
class _Flags:
    on: bool = False


@dataclass
class _Leaky:
    """Exercises everything docs/contract.md's 'What never appears' names.

    A compiled pattern, a file-contract mark, a `default_factory` recipe, an
    enum member as a default, and a field with no default at all.
    """
    token: Annotated[str, Pattern(r"[A-Z]{3}\d+", message="letters then digits")]
    upload: Annotated[str, FileHint(extensions=(".pdf", ".txt"), min_size=1,
                                    max_size=2048)]
    role: _Role = _Role.ADMIN
    tags: list[str] = field(default_factory=lambda: ["a", "b"])
    inner: _Inner = field(default_factory=_Inner)
    when: date = date(2024, 6, 1)
    at: time = time(9, 30, 0)
    # `false` as data rather than as an atom, at the top level and nested in a
    # default: neither is one of the format's three written-false exceptions.
    enabled: bool = False
    flags: _Flags = field(default_factory=_Flags)


def _upload(path: str, when: date = date(2024, 1, 1),
            role: _Role = _Role.USER) -> None:
    """Upload a document."""


def _bare(x: int) -> None:
    # No docstring on purpose: `doc` is "omitted when the function has no
    # docstring".
    return None


def _every_shape(number: int, ratio: float, word: str, flag: bool, day: date,
                 hour: time, maybe: int | None, tags: list[str], role: _Role,
                 inner: _Inner) -> None:
    """One parameter per shape."""


_BATTERY = {
    "user": lambda: struct_of(_User).to_dict(),
    "inner": lambda: struct_of(_Inner).to_dict(),
    "everything": lambda: struct_of(_Everything).to_dict(),
    "unions": lambda: struct_of(_Unions).to_dict(),
    "leaky": lambda: struct_of(_Leaky).to_dict(),
    "signature_with_doc": lambda: signature_of(_upload).to_dict(),
    "signature_without_doc": lambda: signature_of(_bare).to_dict(),
    "signature_every_shape": lambda: signature_of(_every_shape).to_dict(),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# "dicts, lists, strings, numbers, booleans and null, and nothing else."
_JSON_TYPES = (dict, list, str, int, float, bool, type(None))


def _walk(document):
    """Every value in the document, containers included, at every depth."""
    pending = [document]
    while pending:
        value = pending.pop()
        yield value
        if type(value) is dict:
            pending.extend(value.values())
        elif type(value) is list:
            pending.extend(value)


def _paths(value, prefix=()):
    """Every (path, value) pair, where a path is a tuple of keys and indexes."""
    yield prefix, value
    if type(value) is dict:
        for key, item in value.items():
            yield from _paths(item, prefix + (key,))
    elif type(value) is list:
        for index, item in enumerate(value):
            yield from _paths(item, prefix + (index,))


def _keys(document):
    """Every mapping key in the document."""
    return [key for value in _walk(document) if type(value) is dict
            for key in value]


def _containers(document):
    return [value for value in _walk(document) if type(value) in (dict, list)]


def _shape_nodes(document):
    """Every shape node: the members of a `shape` slot or an `item` slot."""
    return [value for path, value in _paths(document)
            if len(path) >= 2 and path[-2] in ("shape", "item")
            and type(path[-1]) is int]


def _fields_of(document, struct_id="_Probe"):
    return document["defs"]["structs"][struct_id]["fields"]


def _named(fields, name):
    return next(f for f in fields if f["name"] == name)


def _probe_field(annotation, **spec):
    """The one field node of a one-field dataclass hinted `annotation`."""
    entry = ("value", annotation, field(**spec)) if spec else ("value", annotation)
    probe = make_dataclass("_Probe", [entry])
    return _fields_of(struct_of(probe).to_dict())[0]


def _probe_node(annotation, **spec):
    """The first shape node of that field."""
    return _probe_field(annotation, **spec)["shape"][0]


# ---------------------------------------------------------------------------
# 0. The helpers above must really reach the document
# ---------------------------------------------------------------------------

def test_the_walkers_reach_the_whole_document():
    """The guard that keeps every parametrised sweep below honest."""
    document = struct_of(_Everything).to_dict()

    assert len(_shape_nodes(document)) >= 15
    assert len(_containers(document)) >= 60
    assert any(value is None for _, value in _paths(document))
    assert any(value is False for _, value in _paths(document))
    assert {"extras", "file_hint", "slider", "choices", "pattern",
            "optional_toggle", "default", "ref", "item"} <= set(_keys(document))


def test_every_subject_of_the_battery_is_a_document():
    """Each entry really compiles; a battery that raised on import would sweep nothing."""
    for name, make in _BATTERY.items():
        assert make()["v"] == 1, name


# ---------------------------------------------------------------------------
# 1. The root document
# ---------------------------------------------------------------------------

def test_struct_document_reproduces_the_documented_example_exactly():
    """docs/contract.md opens with `struct_of(User).to_dict()` written out in full."""
    assert struct_of(_User).to_dict() == {
        "v": 1, "kind": "struct", "root": "_User",
        "defs": {"structs": {"_User": {"name": "_User", "fields": [
            {"name": "name", "shape": [{"type": "str"}]},
            {"name": "birthday", "shape": [{"type": "date"}]}]}},
            "enums": {}}}


def test_struct_document_writes_its_four_keys_in_the_documented_order():
    """'{"v": 1, "kind": "struct", "root": "Cart", "defs": {…}}'."""
    assert list(struct_of(_Everything).to_dict()) == ["v", "kind", "root", "defs"]


def test_signature_document_writes_its_keys_in_the_documented_order():
    """'{"v": 1, "kind": "signature", "name": …, "doc": …, "params": …, "defs": …}'."""
    assert list(signature_of(_upload).to_dict()) == [
        "v", "kind", "name", "doc", "params", "defs"]


def test_signature_omits_doc_when_the_function_has_no_docstring():
    """docs/contract.md: `doc` is 'omitted when the function has no docstring'."""
    document = signature_of(_bare).to_dict()

    assert "doc" not in document
    assert list(document) == ["v", "kind", "name", "params", "defs"]


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_every_document_declares_format_version_one(make):
    """'`v` is the version of the *format*, never of the library.'"""
    assert make()["v"] == 1
    assert type(make()["v"]) is int


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_kind_tells_the_two_documents_apart(make):
    """docs/contract.md, 'Documents': 'Two kinds, told apart by `kind`.'"""
    assert make()["kind"] in ("struct", "signature")


def test_struct_root_names_an_id_in_defs_structs():
    """'"root": "Cart",  // an id in defs.structs'."""
    document = struct_of(_Everything).to_dict()

    assert document["root"] in document["defs"]["structs"]


def test_signature_name_is_an_identifier_and_there_is_no_root():
    """A signature carries a `name`; only a struct document carries a `root`."""
    document = signature_of(_upload).to_dict()

    assert document["name"] == "_upload"
    assert "root" not in document


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_defs_is_always_present_with_both_tables(make):
    """'`defs` is always present with both tables, even empty.'"""
    document = make()

    assert list(document["defs"]) == ["structs", "enums"]
    assert type(document["defs"]["structs"]) is dict
    assert type(document["defs"]["enums"]) is dict


def test_defs_tables_are_empty_rather_than_absent_when_nothing_is_defined():
    """'a shape that varies would make every reader write doc.get("defs", {})…'."""
    document = signature_of(_bare).to_dict()

    assert document["defs"] == {"structs": {}, "enums": {}}


def test_signature_writes_its_parameters_in_place_not_as_a_definition():
    """'A signature's parameters are written in place, because nothing can hold a reference to a signature.'"""
    document = signature_of(_upload).to_dict()

    assert [p["name"] for p in document["params"]] == ["path", "when", "role"]
    assert document["defs"]["structs"] == {}


def test_a_struct_definition_carries_name_and_fields_in_that_order():
    """'"Cart": {"name": "Cart", "fields": [ <field>, … ]}'."""
    definition = struct_of(_User).to_dict()["defs"]["structs"]["_User"]

    assert list(definition) == ["name", "fields"]
    assert definition["name"] == "_User"


def test_an_enum_definition_carries_name_and_members_in_definition_order():
    """'"Role": {"name": "Role", "members": ["ADMIN", "USER"]}  // canonical members, in definition order'."""
    definition = struct_of(_Everything).to_dict()["defs"]["enums"]["_Role"]

    assert list(definition) == ["name", "members"]
    assert definition == {"name": "_Role", "members": ["ADMIN", "USER"]}


def test_a_field_writes_its_keys_in_the_documented_order():
    """docs/contract.md, 'Fields': name, label, description, optional_toggle, default, shape."""
    document = struct_of(_Everything).to_dict()
    described = _named(_fields_of(document, "_Everything"), "described")
    maybe = _named(_fields_of(document, "_Everything"), "maybe")

    assert list(described) == ["name", "label", "description", "shape"]
    assert list(maybe) == ["name", "optional_toggle", "default", "shape"]


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_shape_is_always_an_array_with_at_least_one_option(make):
    """'`shape` is an array even for a single option, so a reader has one code path rather than two.'"""
    for path, value in _paths(make()):
        if path and path[-1] in ("shape", "item"):
            assert type(value) is list, path
            assert value, path


# ---------------------------------------------------------------------------
# 2. One node per shape
# ---------------------------------------------------------------------------

_SHAPES = [
    ("int", int, "int"),
    ("float", float, "float"),
    ("str", str, "str"),
    ("bool", bool, "bool"),
    ("date", date, "date"),
    ("time", time, "time"),
    ("list", list[str], "list"),
    ("enum", _Role, "enum"),
    ("struct", _Inner, "struct"),
]


@pytest.mark.parametrize("annotation, expected", [(a, e) for _, a, e in _SHAPES],
                         ids=[i for i, _, _ in _SHAPES])
def test_every_shape_writes_its_documented_type(annotation, expected):
    """'`type` is one of `int`, `float`, `str`, `bool`, `date`, `time`, `none`, `list`, `enum`, `struct`.'"""
    assert _probe_node(annotation)["type"] == expected


def test_the_none_shape_writes_type_none():
    """A `none` option only ever sits beside another, and it is written `{"type": "none"}`."""
    assert _probe_field(int | None, default=None)["shape"][1]["type"] == "none"


_BARE = [("int", int), ("float", float), ("str", str), ("bool", bool),
         ("date", date), ("time", time)]


@pytest.mark.parametrize("annotation", [a for _, a in _BARE],
                         ids=[i for i, _ in _BARE])
def test_a_shape_without_atoms_writes_only_its_type(annotation):
    """'An absent atom omits its key. It is never written as `null`.'"""
    assert _probe_node(annotation) == {"type": annotation.__name__}


def test_a_bare_list_writes_only_its_type_and_its_item_slot():
    """'{"type": "list", "id": …, "min_items": …, "max_items": …, "item": […]}' — with nothing narrowing it, only `item` survives."""
    assert _probe_node(list[str]) == {"type": "list", "item": [{"type": "str"}]}


def test_a_bare_enum_writes_only_its_type_and_ref():
    """'{"type": "enum", "id": …, "ref": "Role", "extras": {…}}'."""
    assert _probe_node(_Role) == {"type": "enum", "ref": "_Role"}


def test_a_struct_node_is_only_a_type_and_a_ref():
    """'A `Struct` node never has extras; the vocabulary does not admit atoms on a nested dataclass.'"""
    assert _probe_node(_Inner) == {"type": "struct", "ref": "_Inner"}


def test_a_none_node_is_only_a_type_and_its_id():
    """'{"type": "none", "id": "None", "extras": {…}}'."""
    assert _probe_field(int | None, default=None)["shape"][1] == {
        "type": "none", "id": "None"}


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_type_is_the_first_key_of_every_node(make):
    """Every node in the format is listed starting at `type`."""
    for node in _shape_nodes(make()):
        assert list(node)[0] == "type"


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_no_node_carries_a_type_outside_the_documented_ten(make):
    """'`type` is one of int, float, str, bool, date, time, none, list, enum, struct.'"""
    documented = {"int", "float", "str", "bool", "date", "time", "none",
                  "list", "enum", "struct"}
    for node in _shape_nodes(make()):
        assert node["type"] in documented


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_every_struct_node_is_a_reference_and_never_carries_extras(make):
    """'Always a reference, never inlined' — plus 'A `Struct` node never has extras'."""
    for node in _shape_nodes(make()):
        if node["type"] == "struct":
            assert set(node) <= {"type", "id", "ref"}


def test_a_slot_uses_item_and_never_items():
    """'`item`, not `items`.' — in JSON Schema `items` means positional validation of a tuple."""
    node = _probe_node(list[str])

    assert "item" in node
    assert "items" not in node


@pytest.mark.parametrize("annotation, expected", [(_Role, "enum"), (_Inner, "struct")],
                         ids=["enum", "struct"])
def test_a_definition_is_pointed_at_by_ref_and_never_by_dollar_ref(annotation, expected):
    """'`ref`, not `$ref`.' — `$` marks reserved keys in *data*, not schema metadata."""
    node = _probe_node(annotation)

    assert node["type"] == expected
    assert "ref" in node and "$ref" not in node


# ---------------------------------------------------------------------------
# 3. One atom at a time
# ---------------------------------------------------------------------------

_ATOMS = {
    # Min/Max on the ordered shapes -> min/max, exclusive only when exclusive.
    "int_min": (Annotated[int, Min(0)], {"type": "int", "min": 0}),
    "int_min_exclusive": (Annotated[int, Min(0, exclusive=True)],
                          {"type": "int", "min": 0, "exclusive_min": True}),
    "int_max": (Annotated[int, Max(10)], {"type": "int", "max": 10}),
    "int_max_exclusive": (Annotated[int, Max(10, exclusive=True)],
                          {"type": "int", "max": 10, "exclusive_max": True}),
    "float_min": (Annotated[float, Min(0.0)], {"type": "float", "min": 0.0}),
    "float_min_exclusive": (Annotated[float, Min(0.0, exclusive=True)],
                            {"type": "float", "min": 0.0, "exclusive_min": True}),
    "float_max": (Annotated[float, Max(1.0)], {"type": "float", "max": 1.0}),
    "float_max_exclusive": (Annotated[float, Max(1.0, exclusive=True)],
                            {"type": "float", "max": 1.0, "exclusive_max": True}),
    "date_min": (Annotated[date, Min(date(2024, 1, 1))],
                 {"type": "date", "min": "2024-01-01"}),
    "date_min_exclusive": (Annotated[date, Min(date(2024, 1, 1), exclusive=True)],
                           {"type": "date", "min": "2024-01-01", "exclusive_min": True}),
    "date_max": (Annotated[date, Max(date(2024, 12, 31))],
                 {"type": "date", "max": "2024-12-31"}),
    "date_max_exclusive": (Annotated[date, Max(date(2024, 12, 31), exclusive=True)],
                           {"type": "date", "max": "2024-12-31", "exclusive_max": True}),
    # docs/contract.md's `time` listing abbreviates: it shows `min`/`max`
    # without the exclusive pair the `date` listing spells out. The prose rules
    # for both — only `str` and `list` are told "exclusive_min and exclusive_max
    # cannot appear" — so an exclusive time bound is written like any other.
    "time_min": (Annotated[time, Min(time(9, 0))],
                 {"type": "time", "min": "09:00:00"}),
    "time_min_exclusive": (Annotated[time, Min(time(9, 0), exclusive=True)],
                           {"type": "time", "min": "09:00:00", "exclusive_min": True}),
    "time_max": (Annotated[time, Max(time(18, 0))],
                 {"type": "time", "max": "18:00:00"}),
    "time_max_exclusive": (Annotated[time, Max(time(18, 0), exclusive=True)],
                           {"type": "time", "max": "18:00:00", "exclusive_max": True}),
    # Min/Max on str -> min_length/max_length; on list -> min_items/max_items.
    "str_min_length": (Annotated[str, Min(1)], {"type": "str", "min_length": 1}),
    "str_max_length": (Annotated[str, Max(20)], {"type": "str", "max_length": 20}),
    "list_min_items": (Annotated[list[str], Min(0)],
                       {"type": "list", "min_items": 0, "item": [{"type": "str"}]}),
    "list_max_items": (Annotated[list[str], Max(10)],
                       {"type": "list", "max_items": 10, "item": [{"type": "str"}]}),
    # Choices, in the author's order.
    "int_choices": (Annotated[int, Choices(values=(3, 1, 2))],
                    {"type": "int", "choices": [3, 1, 2]}),
    "float_choices": (Annotated[float, Choices(values=(3.5, 1.5, 2.5))],
                      {"type": "float", "choices": [3.5, 1.5, 2.5]}),
    "str_choices": (Annotated[str, Choices(values=("c", "a", "b"))],
                    {"type": "str", "choices": ["c", "a", "b"]}),
    "date_choices": (Annotated[date, Choices(values=(date(2024, 6, 1), date(2024, 1, 1)))],
                     {"type": "date", "choices": ["2024-06-01", "2024-01-01"]}),
    "time_choices": (Annotated[time, Choices(values=(time(18, 0), time(9, 0)))],
                     {"type": "time", "choices": ["18:00:00", "09:00:00"]}),
    # The rest, one atom each.
    "multiple_of": (Annotated[int, MultipleOf(5)],
                    {"type": "int", "multiple_of": 5}),
    "pattern": (Annotated[str, Pattern("[a-z]+")],
                {"type": "str", "pattern": "[a-z]+"}),
    "pattern_with_message": (Annotated[str, Pattern("[a-z]+", message="lowercase")],
                             {"type": "str", "pattern": "[a-z]+",
                              "pattern_message": "lowercase"}),
    "file_hint_bare": (Annotated[str, FileHint()],
                       {"type": "str", "file_hint": {}}),
    "file_hint_extensions": (Annotated[str, FileHint(extensions=(".pdf", ".txt"))],
                             {"type": "str",
                              "file_hint": {"extensions": [".pdf", ".txt"]}}),
    "file_hint_min_size": (Annotated[str, FileHint(min_size=0)],
                           {"type": "str", "file_hint": {"min_size": 0}}),
    "file_hint_max_size": (Annotated[str, FileHint(max_size=1048576)],
                           {"type": "str", "file_hint": {"max_size": 1048576}}),
    "file_hint_full": (Annotated[str, FileHint(extensions=(".pdf",), min_size=0,
                                               max_size=1048576)],
                       {"type": "str",
                        "file_hint": {"extensions": [".pdf"], "min_size": 0,
                                      "max_size": 1048576}}),
    "is_password": (Annotated[str, IsPassword()],
                    {"type": "str", "is_password": True}),
    "rows": (Annotated[str, Rows(5)], {"type": "str", "rows": 5}),
    "int_step": (Annotated[int, Step(5)], {"type": "int", "step": 5}),
    "float_step": (Annotated[float, Step(0.01)], {"type": "float", "step": 0.01}),
    "int_placeholder": (Annotated[int, Placeholder("p")],
                        {"type": "int", "placeholder": "p"}),
    "str_placeholder": (Annotated[str, Placeholder("p")],
                        {"type": "str", "placeholder": "p"}),
    "date_placeholder": (Annotated[date, Placeholder("p")],
                         {"type": "date", "placeholder": "p"}),
    "time_placeholder": (Annotated[time, Placeholder("p")],
                         {"type": "time", "placeholder": "p"}),
    "slider_showing_its_value": (Annotated[int, Min(0), Max(10), Slider()],
                                 {"type": "int", "min": 0, "max": 10,
                                  "slider": {"show_value": True}}),
    "slider_hiding_its_value": (Annotated[int, Min(0), Max(10),
                                          Slider(show_value=False)],
                                {"type": "int", "min": 0, "max": 10,
                                 "slider": {"show_value": False}}),
    "extras": (Annotated[str, Extra("b.key", "2"), Extra("a.key", "1")],
               {"type": "str", "extras": {"a.key": "1", "b.key": "2"}}),
}


@pytest.mark.parametrize("annotation, expected", list(_ATOMS.values()),
                         ids=list(_ATOMS))
def test_each_atom_is_written_under_its_documented_key(annotation, expected):
    """docs/contract.md, 'Shape nodes': the key each atom writes, and nothing beside it."""
    assert _probe_node(annotation) == expected


@pytest.mark.parametrize("annotation", [
    Annotated[int, Min(0), Max(10)],
    Annotated[float, Min(0.0), Max(1.0)],
    Annotated[date, Min(date(2024, 1, 1)), Max(date(2024, 12, 31))],
    Annotated[time, Min(time(9, 0)), Max(time(18, 0))],
], ids=["int", "float", "date", "time"])
def test_an_inclusive_bound_never_writes_exclusive_false(annotation):
    """'Values equal to their own default are omitted too — no `"exclusive_min": false`.'"""
    node = _probe_node(annotation)

    assert "exclusive_min" not in node
    assert "exclusive_max" not in node


@pytest.mark.parametrize("annotation", [
    Annotated[str, Min(1), Max(20)],
    Annotated[list[str], Min(1), Max(20)],
], ids=["str", "list"])
def test_a_length_bound_is_never_spelled_min_or_max_nor_marked_exclusive(annotation):
    """'`exclusive_min` and `exclusive_max` cannot appear on either' — nor may a length be called `min`."""
    node = _probe_node(annotation)

    assert "min" not in node and "max" not in node
    assert "exclusive_min" not in node and "exclusive_max" not in node


@pytest.mark.parametrize("annotation, expected", [
    (Annotated[int, Choices(values=(3, 1, 2))], [3, 1, 2]),
    (Annotated[float, Choices(values=(3.5, 1.5, 2.5))], [3.5, 1.5, 2.5]),
    (Annotated[str, Choices(values=("c", "a", "b"))], ["c", "a", "b"]),
    (Annotated[date, Choices(values=(date(2024, 6, 1), date(2024, 1, 1)))],
     ["2024-06-01", "2024-01-01"]),
    (Annotated[time, Choices(values=(time(18, 0), time(9, 0)))],
     ["18:00:00", "09:00:00"]),
], ids=["int", "float", "str", "date", "time"])
def test_choices_keep_the_order_the_author_wrote(annotation, expected):
    """'every sequence keeps the order the author wrote' — never sorted."""
    assert _probe_node(annotation)["choices"] == expected


@pytest.mark.parametrize("annotation, key, expected", [
    (Annotated[date, Min(date(2024, 1, 1))], "min", "2024-01-01"),
    (Annotated[date, Max(date(2024, 12, 31))], "max", "2024-12-31"),
    (Annotated[time, Min(time(9, 0))], "min", "09:00:00"),
    (Annotated[time, Max(time(18, 0, 5))], "max", "18:00:05"),
], ids=["date_min", "date_max", "time_min", "time_max"])
def test_a_date_or_time_bound_is_written_the_way_decode_reads_one(annotation, key,
                                                                 expected):
    """'A date is written the way `decode` reads one' — "YYYY-MM-DD" and "HH:MM:SS"."""
    value = _probe_node(annotation)[key]

    assert value == expected
    assert type(value) is str


def test_multiple_of_belongs_to_int_alone():
    """docs/contract.md lists `multiple_of` only in the `int` node."""
    assert _probe_node(Annotated[int, MultipleOf(5)])["multiple_of"] == 5

    for name, (annotation, _) in _ATOMS.items():
        node = _probe_node(annotation)
        if node["type"] != "int":
            assert "multiple_of" not in node, name


def test_pattern_message_is_omitted_when_the_pattern_carries_none():
    """'`pattern` … `pattern_message`' — the second is an atom of its own and absent when unset."""
    assert "pattern_message" not in _probe_node(Annotated[str, Pattern("[a-z]+")])


def test_slider_is_an_object_and_never_a_bare_boolean():
    """'`slider` is an object, never a bare boolean: `show_value: false` would otherwise read as "no slider".'"""
    node = _probe_node(Annotated[int, Min(0), Max(10), Slider(show_value=False)])

    assert node["slider"] == {"show_value": False}
    assert type(node["slider"]) is dict


def test_is_password_is_written_true_and_never_false():
    """'`is_password": true' — the mark is written only when it is there."""
    assert _probe_node(Annotated[str, IsPassword()])["is_password"] is True
    assert "is_password" not in _probe_node(str)


def test_file_hint_writes_its_own_keys_in_the_documented_order():
    """'"file_hint": {"extensions": [".pdf"], "min_size": 0, "max_size": 1048576}'."""
    mark = _probe_node(Annotated[str, FileHint(extensions=(".pdf",), min_size=0,
                                               max_size=1048576)])["file_hint"]

    assert list(mark) == ["extensions", "min_size", "max_size"]


def test_file_hint_keeps_the_extensions_in_the_order_the_author_wrote():
    """'every sequence keeps the order the author wrote'."""
    mark = _probe_node(Annotated[str, FileHint(extensions=(".txt", ".pdf"))])["file_hint"]

    assert mark["extensions"] == [".txt", ".pdf"]


def test_file_hint_with_nothing_narrowing_it_is_an_empty_object():
    """'`"file_hint": {}` — the mark itself, with nothing narrowing it.'"""
    assert _probe_node(Annotated[str, FileHint()])["file_hint"] == {}


@pytest.mark.parametrize("label, description, expected", [
    (Label("L"), None, {"label": "L"}),
    (None, Description("D"), {"description": "D"}),
    (Label("L"), Description("D"), {"label": "L", "description": "D"}),
    (None, None, {}),
], ids=["label", "description", "both", "neither"])
def test_label_and_description_live_on_the_field_and_are_omitted_when_absent(
        label, description, expected):
    """docs/contract.md, 'Fields': '"label": "Age",  // omitted when absent'."""
    atoms = tuple(a for a in (label, description) if a is not None)
    annotation = Annotated[(str, *atoms)] if atoms else str
    node = _probe_field(annotation)

    assert {k: v for k, v in node.items() if k in ("label", "description")} == expected


@pytest.mark.parametrize("toggle, expected", [
    (OptionalToggle(True), True),
    (OptionalToggle(False), False),
], ids=["true", "false"])
def test_optional_toggle_writes_both_of_its_values(toggle, expected):
    """'"optional_toggle": false,  // omitted when absent; false is written'."""
    node = _probe_field(Annotated[int | None, toggle], default=None)

    assert node["optional_toggle"] is expected


def test_optional_toggle_is_omitted_when_the_author_never_wrote_one():
    """'absent, true and false are three states' — the third one omits the key."""
    assert "optional_toggle" not in _probe_field(int | None, default=None)


def test_extras_is_the_last_key_of_a_node_and_omitted_when_empty():
    """'`extras` is last on every node, and omitted when empty.'"""
    bare = _probe_node(Annotated[int, Min(0), Max(10), Placeholder("p")])
    annotated = _probe_node(Annotated[int, Min(0), Max(10), Placeholder("p"),
                                      Extra("a.key", "1")])

    assert "extras" not in bare
    assert list(annotated)[-1] == "extras"


def test_extras_keys_are_sorted_and_unique():
    """'Its keys are already sorted and unique.'"""
    node = _probe_node(Annotated[str, Extra("z.key", "3"), Extra("a.key", "1"),
                                 Extra("m.key", "2")])

    assert list(node["extras"]) == ["a.key", "m.key", "z.key"]


def test_pattern_is_written_as_its_source_string():
    """'`pattern` is a Python `re` pattern applied with `fullmatch`. It is portable as a string'."""
    node = _probe_node(Annotated[str, Pattern(r"[A-Z]{3}\d+")])

    assert node["pattern"] == r"[A-Z]{3}\d+"
    assert type(node["pattern"]) is str


_MAXIMAL_NODES = {
    "int": (Annotated[int, Min(0, exclusive=True), Max(15, exclusive=True),
                      MultipleOf(5), Choices(values=(5, 10)), Step(5), Slider(),
                      Placeholder("p"), Extra("a.key", "1")],
            ["type", "min", "exclusive_min", "max", "exclusive_max",
             "multiple_of", "choices", "step", "slider", "placeholder", "extras"]),
    "float": (Annotated[float, Min(0.0, exclusive=True), Max(1.0, exclusive=True),
                        Choices(values=(0.5,)), Step(0.01),
                        Slider(show_value=False), Placeholder("p"),
                        Extra("a.key", "1")],
              ["type", "min", "exclusive_min", "max", "exclusive_max", "choices",
               "step", "slider", "placeholder", "extras"]),
    "str": (Annotated[str, Min(2), Max(20), Pattern("[a-z]+", message="m"),
                      Choices(values=("ab", "cd")), IsPassword(), Rows(5),
                      Placeholder("p"), Extra("a.key", "1")],
            ["type", "min_length", "max_length", "pattern", "pattern_message",
             "choices", "is_password", "rows", "placeholder", "extras"]),
    "str_path": (Annotated[str, Min(2), Max(20),
                           FileHint(extensions=(".pdf",), min_size=0,
                                    max_size=1048576), Placeholder("p"),
                           Extra("a.key", "1")],
                 ["type", "min_length", "max_length", "file_hint",
                  "placeholder", "extras"]),
    "date": (Annotated[date, Min(date(2024, 1, 1), exclusive=True),
                       Max(date(2024, 12, 31), exclusive=True),
                       Choices(values=(date(2024, 6, 1),)), Placeholder("p"),
                       Extra("a.key", "1")],
             ["type", "min", "exclusive_min", "max", "exclusive_max", "choices",
              "placeholder", "extras"]),
    "time": (Annotated[time, Min(time(9, 0), exclusive=True),
                       Max(time(18, 0), exclusive=True),
                       Choices(values=(time(10, 0),)), Placeholder("p"),
                       Extra("a.key", "1")],
             ["type", "min", "exclusive_min", "max", "exclusive_max", "choices",
              "placeholder", "extras"]),
    "list": (Annotated[list[str], Min(0), Max(10), Extra("a.key", "1")],
             ["type", "min_items", "max_items", "item", "extras"]),
    "enum": (Annotated[_Role, Extra("a.key", "1")], ["type", "ref", "extras"]),
    "bool": (Annotated[bool, Extra("a.key", "1")], ["type", "extras"]),
}


@pytest.mark.parametrize("annotation, order", list(_MAXIMAL_NODES.values()),
                         ids=list(_MAXIMAL_NODES))
def test_a_fully_annotated_node_writes_its_keys_in_the_documented_order(annotation,
                                                                       order):
    """'Every key is written in a fixed order' — docs/contract.md, 'Shape nodes'."""
    assert list(_probe_node(annotation)) == order


# ---------------------------------------------------------------------------
# 4. Float is canonical
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("written_as_int, written_as_float", [
    (Annotated[float, Min(0)], Annotated[float, Min(0.0)]),
    (Annotated[float, Max(1)], Annotated[float, Max(1.0)]),
    (Annotated[float, Step(1)], Annotated[float, Step(1.0)]),
    (Annotated[float, Min(0), Max(1), Step(1)],
     Annotated[float, Min(0.0), Max(1.0), Step(1.0)]),
], ids=["min", "max", "step", "all_three"])
def test_equal_float_shapes_produce_equal_documents_however_the_bound_was_typed(
        written_as_int, written_as_float):
    """'Equal definitions produce equal documents, byte for byte.' `Min(0)` and `Min(0.0)` are one shape."""
    from_int = _probe_node(written_as_int)
    from_float = _probe_node(written_as_float)

    assert from_int == from_float
    assert json.dumps(from_int) == json.dumps(from_float)


@pytest.mark.parametrize("annotation, key", [
    (Annotated[float, Min(0)], "min"),
    (Annotated[float, Max(1)], "max"),
    (Annotated[float, Step(1)], "step"),
], ids=["min", "max", "step"])
def test_a_float_node_writes_floats_even_where_the_author_wrote_an_int(annotation, key):
    """'{"type": "float", … "min": 0.0, … "step": 0.01}' — a float node carries floats."""
    value = _probe_node(annotation)[key]

    assert type(value) is float


def test_every_number_in_a_float_node_is_a_float():
    """The whole node at once: nothing numeric in a `float` node is written as an int."""
    node = _probe_node(Annotated[float, Min(0), Max(10), Step(1),
                                 Choices(values=(0.0, 5.0, 10.0))])

    numbers = [node["min"], node["max"], node["step"], *node["choices"]]
    assert all(type(n) is float for n in numbers)


def test_an_int_node_keeps_its_ints():
    """The mirror of the rule above: `int` is not folded into `float`."""
    node = _probe_node(Annotated[int, Min(0), Max(10), Step(1), MultipleOf(5),
                                 Choices(values=(0, 5, 10))])

    numbers = [node["min"], node["max"], node["step"], node["multiple_of"],
               *node["choices"]]
    assert all(type(n) is int for n in numbers)


# ---------------------------------------------------------------------------
# 5. `id`
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("annotation", [int, float, str, bool, date, time,
                                        list[str], _Role, _Inner],
                         ids=["int", "float", "str", "bool", "date", "time",
                              "list", "enum", "struct"])
def test_id_is_absent_where_a_slot_holds_a_single_option(annotation):
    """'It is written only where the slot holds two or more options, because that is the only place anything reads it.'"""
    assert "id" not in _probe_node(annotation)


def test_id_is_absent_in_a_list_item_slot_of_a_single_option():
    """The `item` slot is a slot like any other: one option, no `id`."""
    assert "id" not in _probe_node(list[str])["item"][0]


@pytest.mark.parametrize("annotation, expected", [
    (int | None, ["int", "None"]),
    (int | float, ["int", "float"]),
    (str | date, ["str", "date"]),
    (list[str] | None, ["list[str]", "None"]),
    (list[int | None] | None, ["list[int | None]", "None"]),
    (list[list[str]] | None, ["list[list[str]]", "None"]),
    (_Role | None, ["_Role", "None"]),
    (_Inner | None, ["_Inner", "None"]),
], ids=["int_none", "int_float", "str_date", "list_str", "list_int_none",
        "list_of_list", "enum_none", "struct_none"])
def test_every_option_of_a_shared_slot_writes_its_option_id(annotation, expected):
    """'`id` is `Shape.option_id()` — the identity a discriminator names.'"""
    node = _probe_field(annotation, default=None) if type(None) in getattr(
        annotation, "__args__", ()) else _probe_field(annotation)

    assert [option["id"] for option in node["shape"]] == expected


def test_the_none_shape_is_identified_as_the_string_none():
    """'{"type": "none", "id": "None"}'."""
    assert _probe_field(int | None, default=None)["shape"][1]["id"] == "None"


def test_a_list_spells_its_items_into_its_own_id():
    """docs/restrictions.md, quoted by the format: 'a list spells out its items: list[str], list[int], list[list[str]]'."""
    assert _probe_field(list[str] | None, default=None)["shape"][0]["id"] == "list[str]"
    assert _probe_field(list[list[str]] | None,
                        default=None)["shape"][0]["id"] == "list[list[str]]"


def test_an_item_slot_of_two_options_labels_both():
    """A union inside a list is a slot of two options, so both carry an `id`."""
    node = _probe_field(list[int | None] | None, default=None)["shape"][0]

    assert [option["id"] for option in node["item"]] == ["int", "None"]


def test_id_directly_follows_type_when_it_is_written():
    """'{"type": "int", "id": …, "min": 0, …}' — `id` sits second."""
    for option in _probe_field(int | float)["shape"]:
        assert list(option)[:2] == ["type", "id"]


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_id_appears_exactly_where_the_slot_holds_two_or_more_options(make):
    """One statement of the rule, applied to every slot in the document."""
    for path, value in _paths(make()):
        if path and path[-1] in ("shape", "item") and type(value) is list:
            for option in value:
                assert ("id" in option) is (len(value) > 1), (path, option)


# ---------------------------------------------------------------------------
# 6. It is JSON
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_the_document_serialises_to_json(make):
    """'a portable tree — dicts, lists, strings, numbers, booleans and null, and nothing else'."""
    json.dumps(make())


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_the_document_survives_a_json_round_trip_unchanged(make):
    """Nothing in the tree loses its identity through JSON, so a document is what it serialises to."""
    document = make()

    assert json.loads(json.dumps(document)) == document


@pytest.mark.parametrize("annotation",
                         [annotation for annotation, _ in _ATOMS.values()],
                         ids=list(_ATOMS))
def test_every_single_atom_schema_serialises_to_json(annotation):
    """Atom by atom: none of them writes a value JSON cannot carry."""
    document = struct_of(make_dataclass("_Probe", [("value", annotation)])).to_dict()

    assert json.loads(json.dumps(document)) == document


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_every_mapping_key_in_the_document_is_a_string(make):
    """A JSON object has string keys; anything else would not survive a dump."""
    for key in _keys(make()):
        assert type(key) is str, key


# ---------------------------------------------------------------------------
# 7. Nothing of the implementation leaks
# ---------------------------------------------------------------------------

# docs/contract.md, 'What never appears'.
_FORBIDDEN_TYPE_NAMES = {
    "Pattern",                                  # the compiled re.Pattern
    "type", "ABCMeta", "EnumType", "EnumMeta",  # class objects
    "_Role", "Enum",                            # raw enum members
    "Path", "PosixPath", "WindowsPath",         # filesystem paths
    "function", "method", "builtin_function_or_method", "lambda",
    "_Factory", "_MissingType",
    "tuple", "set", "frozenset", "bytes",
    "date", "time", "datetime",                 # written as ISO strings, never raw
    "Struct", "Field", "EnumShape", "Int", "Float", "Str", "Bool", "List",
    "NoneShape", "Signature",
}

# Implementation attributes that must not become keys.
_FORBIDDEN_KEYS = {
    "_recipe", "_deferred", "_extras", "_compiled", "cls", "pytype",
    "__module__", "__qualname__", "__doc__", "MISSING",
}


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_every_value_in_the_document_is_a_json_primitive(make):
    """'dicts, lists, strings, numbers, booleans and null, and nothing else.'"""
    strays = {type(value).__name__ for value in _walk(make())
              if type(value) not in _JSON_TYPES}

    assert not strays, f"non-JSON values reached the document: {sorted(strays)}"


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_none_of_the_types_the_format_forbids_reaches_the_document(make):
    """'What never appears': the compiled pattern, the recipe, class objects, paths, methods, tuples, enum values."""
    present = {type(value).__name__ for value in _walk(make())}

    assert not (present & _FORBIDDEN_TYPE_NAMES), sorted(present & _FORBIDDEN_TYPE_NAMES)


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_no_tuple_survives_into_the_document(make):
    """'the tuple form of `extras`' is named among what never appears."""
    assert not [v for v in _walk(make()) if type(v) is tuple]


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_the_missing_sentinel_appears_in_no_spelling(make):
    """'the `MISSING` sentinel in any spelling — it is expressed by omitting `default`.'"""
    document = make()

    assert not [v for v in _walk(document) if v is MISSING]
    assert "MISSING" not in json.dumps(document)


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_no_implementation_attribute_becomes_a_key(make):
    """'Implementation: … the recipe behind a default, the deferred-certification flag … any method'."""
    leaked = sorted(set(_keys(make())) & _FORBIDDEN_KEYS)

    assert not leaked, f"implementation keys in the document: {leaked}"


def test_a_compiled_pattern_never_travels_beside_its_source():
    """'Implementation: the compiled `re.Pattern` behind `pattern`'."""
    node = _named(_fields_of(struct_of(_Leaky).to_dict(), "_Leaky"),
                  "token")["shape"][0]

    assert node["pattern"] == r"[A-Z]{3}\d+"
    assert all(type(value) in _JSON_TYPES for value in _walk(node))


def test_a_default_factory_is_written_as_its_certified_product():
    """'A `default_factory` is not a special case: `Field.default` is the certified *product*.'"""
    fields = _fields_of(struct_of(_Leaky).to_dict(), "_Leaky")

    assert _named(fields, "tags")["default"] == ["a", "b"]
    assert _named(fields, "inner")["default"] == {"x": 1}


def test_an_enum_default_is_written_as_the_member_name():
    """'an enum member by the name decode looks up' — never its value."""
    fields = _fields_of(struct_of(_Leaky).to_dict(), "_Leaky")

    assert _named(fields, "role")["default"] == "ADMIN"


def test_enum_values_never_reach_the_document():
    """'Python identity: … and enum member values.'"""
    document = struct_of(_Leaky).to_dict()

    assert "admin" not in json.dumps(document)
    assert document["defs"]["enums"]["_Role"]["members"] == ["ADMIN", "USER"]


def test_the_document_carries_no_repr_of_anything():
    """'`repr()` of anything.' — no angle-bracketed object repr survives."""
    for name, make in _BATTERY.items():
        assert "<" not in json.dumps(make()), name


def test_the_document_carries_no_provenance():
    """'Provenance: the library version, timestamps, hostnames, the working directory.'"""
    import pytypehint

    for name, make in _BATTERY.items():
        text = json.dumps(make())
        assert pytypehint.__version__ not in text, name
        assert "version" not in set(_keys(make())), name


# ---------------------------------------------------------------------------
# 8. Absence, null and false
# ---------------------------------------------------------------------------

def test_a_field_without_a_default_omits_the_key():
    """'A field with no default omits the key entirely, which is how `MISSING` is expressed.'"""
    node = _probe_field(str)

    assert "default" not in node
    assert list(node) == ["name", "shape"]


def test_a_field_whose_default_is_none_writes_null():
    """'`"default": null` says the default is `None`.'"""
    node = _probe_field(int | None, default=None)

    assert "default" in node
    assert node["default"] is None


def test_no_default_and_a_none_default_are_two_distinguishable_states():
    """'the two are different states and both are real.'"""
    without = _probe_field(int | None)
    with_none = _probe_field(int | None, default=None)

    assert "default" not in without
    assert with_none["default"] is None
    assert without != with_none


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_null_appears_only_as_the_default_of_a_field(make):
    """'`null` therefore means exactly one thing, in exactly one place.'"""
    nulls = [path for path, value in _paths(make()) if value is None]

    assert all(path and path[-1] == "default" for path in nulls), nulls


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_no_atom_is_ever_written_as_null(make):
    """'An absent atom omits its key. It is never written as `null`.'"""
    for node in _shape_nodes(make()):
        assert all(value is not None for value in node.values()), node


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_the_only_false_atoms_written_are_the_documented_exceptions(make):
    """'Three exceptions, each because the value is information': `optional_toggle`, `slider.show_value` — and `file_hint: {}`.

    A `false` inside a `default` is data, not an atom, so it is exempt: the rule
    is about "values equal to their own default", which a default has not got.
    """
    falses = [path for path, value in _paths(make()) if value is False]

    assert all(path[-1] in ("optional_toggle", "show_value") or "default" in path
               for path in falses), falses


def test_a_boolean_default_is_data_and_is_written_wherever_it_sits():
    """'`"default": 18`' — a default is written in the portable language, `false` included."""
    fields = _fields_of(struct_of(_Leaky).to_dict(), "_Leaky")

    assert _named(fields, "enabled")["default"] is False
    assert _named(fields, "flags")["default"] == {"on": False}


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_no_empty_extras_object_is_ever_written(make):
    """'no `"extras": {}`.'"""
    for node in _shape_nodes(make()):
        assert node.get("extras", {"a": "b"}) != {}


def test_the_empty_object_of_file_hint_is_the_one_empty_mapping_allowed_in_a_node():
    """'`"file_hint": {}` — the mark itself, with nothing narrowing it.'"""
    document = struct_of(_Everything).to_dict()
    fields = _fields_of(document, "_Everything")

    assert _named(fields, "anything")["shape"][0]["file_hint"] == {}
    for node in _shape_nodes(document):
        empty = [k for k, v in node.items() if v == {} and k != "file_hint"]
        assert not empty, empty


# ---------------------------------------------------------------------------
# 9. The format does not interpret
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_no_node_carries_optional_required_or_nullable(make):
    """'There is no `optional` or `required` key' — 'Interpretation: `optional`, `required`, `nullable` …'."""
    forbidden = {"optional", "required", "nullable"}
    present = set(_keys(make())) & forbidden

    assert not present, sorted(present)


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_the_format_carries_no_presentation_vocabulary(make):
    """'the format carries no `inputType`, no widget, no label text of its own, no HTML, no CSS, no ordering hints, no layout, and no message strings.'"""
    forbidden = {"inputType", "input_type", "widget", "control", "html", "css",
                 "order", "layout", "message", "messages", "title", "format"}
    present = set(_keys(make())) & forbidden

    assert not present, sorted(present)


def test_an_optional_field_is_described_and_never_flattened():
    """'Interpretation: … flattening, traversal indexes, or the "real option" of an `X | None`.'"""
    node = _probe_field(int | None, default=None)

    assert [option["type"] for option in node["shape"]] == ["int", "none"]


# ---------------------------------------------------------------------------
# 10. Determinism and freshness
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_two_calls_produce_equal_documents(make):
    """'a = struct_of(User).to_dict(); b = struct_of(User).to_dict(); assert json.dumps(a) == json.dumps(b)'."""
    assert make() == make()


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_two_calls_serialise_byte_for_byte_without_sort_keys(make):
    """'`json.dumps` needs no `sort_keys`.'"""
    assert json.dumps(make()) == json.dumps(make())


def test_the_same_schema_object_answers_twice_with_equal_documents():
    """'Nothing is cached between calls. Two callers never receive the same tree.'"""
    schema = struct_of(_Everything)

    assert schema.to_dict() == schema.to_dict()
    assert schema.to_dict() is not schema.to_dict()


@pytest.mark.parametrize("make", list(_BATTERY.values()), ids=list(_BATTERY))
def test_no_container_is_shared_between_two_calls(make):
    """'Nothing in the result is an object the schema holds, at any depth, so the caller owns it completely.'"""
    first, second = make(), make()

    assert not ({id(c) for c in _containers(first)}
                & {id(c) for c in _containers(second)})


def test_clearing_the_definition_table_is_harmless():
    """'document["defs"]["structs"].clear()  # harmless'."""
    schema = struct_of(_Everything)
    original = schema.to_dict()

    document = schema.to_dict()
    document["defs"]["structs"].clear()

    assert schema.to_dict() == original


@pytest.mark.parametrize("mutate", [
    lambda d: d.clear(),
    lambda d: d["defs"]["enums"].clear(),
    lambda d: _fields_of(d, "_Everything").clear(),
    lambda d: _named(_fields_of(d, "_Everything"), "number")["shape"][0].clear(),
    lambda d: _named(_fields_of(d, "_Everything"), "number")["shape"][0]["choices"].append(99),
    lambda d: _named(_fields_of(d, "_Everything"), "number")["shape"][0]["extras"].clear(),
    lambda d: _named(_fields_of(d, "_Everything"), "number")["shape"][0]["slider"].clear(),
    lambda d: _named(_fields_of(d, "_Everything"), "report")["shape"][0]["file_hint"].clear(),
    lambda d: _named(_fields_of(d, "_Everything"), "tags")["shape"][0]["item"].clear(),
    lambda d: d["defs"]["structs"]["_Inner"]["fields"].append({"name": "hi"}),
], ids=["root", "enums", "fields", "node", "choices", "extras", "slider",
        "file_hint", "item", "nested_struct"])
def test_mutating_the_result_at_any_depth_leaves_the_schema_untouched(mutate):
    """'Each call returns a fresh tree. Nothing in the result is an object the schema holds, at any depth.'"""
    schema = struct_of(_Everything)
    original = schema.to_dict()

    mutate(schema.to_dict())

    assert schema.to_dict() == original


# A separate process is the only place the hash seed is free to differ, and the
# subject is written out in full so nothing about it depends on this module.
_IN_ANOTHER_PROCESS = """
import json
from dataclasses import dataclass, field
from datetime import date, time
from enum import Enum
from typing import Annotated
from pytypehint import Extra, Max, Min, struct_of

class Role(Enum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"

@dataclass
class Nested:
    x: int = 1

@dataclass
class Subject:
    tag: Annotated[str, Extra("z.key", "3"), Extra("a.key", "1"), Extra("m.key", "2")]
    role: Role
    nested: Nested
    span: Annotated[int, Min(0), Max(10)]
    day: date = date(2024, 6, 1)
    at: time = time(9, 30, 0)
    tags: list[str] = field(default_factory=lambda: ["b", "a"])

print(json.dumps(struct_of(Subject).to_dict()))
"""


def _document_from_a_fresh_process(seed: str) -> str:
    environment = {**os.environ, "PYTHONHASHSEED": seed}
    result = subprocess.run([sys.executable, "-c", _IN_ANOTHER_PROCESS],
                            capture_output=True, text=True, env=environment,
                            cwd=os.path.dirname(os.path.dirname(__file__)))
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.mark.parametrize("seed", ["1", "12345"], ids=["one", "large"])
def test_the_document_is_the_same_under_any_hash_seed(seed):
    """'Equal definitions produce equal documents, byte for byte, across processes and hash seeds.'"""
    assert _document_from_a_fresh_process(seed) == _document_from_a_fresh_process("0")


def test_two_equal_definitions_written_apart_produce_the_same_document():
    """'Equal definitions produce equal documents, byte for byte, across processes and hash seeds.'"""
    one = make_dataclass("_Twin", [("a", str), ("b", Annotated[int, Min(0)])])
    other = make_dataclass("_Twin", [("a", str), ("b", Annotated[int, Min(0)])])

    assert json.dumps(struct_of(one).to_dict()) == json.dumps(struct_of(other).to_dict())


# ---------------------------------------------------------------------------
# 11. Signature.to_dict
# ---------------------------------------------------------------------------

def test_a_signature_writes_its_docstring_under_doc():
    """'"doc": "Upload a document.",  // omitted when the function has no docstring'."""
    assert signature_of(_upload).to_dict()["doc"] == "Upload a document."


def test_a_signature_keeps_its_parameters_in_declaration_order():
    """'every sequence keeps the order the author wrote'."""
    document = signature_of(_every_shape).to_dict()

    assert [p["name"] for p in document["params"]] == [
        "number", "ratio", "word", "flag", "day", "hour", "maybe", "tags",
        "role", "inner"]


_SIGNATURE_PARAMS = {
    "int": ("number", ["int"]),
    "float": ("ratio", ["float"]),
    "str": ("word", ["str"]),
    "bool": ("flag", ["bool"]),
    "date": ("day", ["date"]),
    "time": ("hour", ["time"]),
    "none": ("maybe", ["int", "none"]),
    "list": ("tags", ["list"]),
    "enum": ("role", ["enum"]),
    "struct": ("inner", ["struct"]),
}


@pytest.mark.parametrize("name, types", list(_SIGNATURE_PARAMS.values()),
                         ids=list(_SIGNATURE_PARAMS))
def test_a_signature_parameter_describes_its_shape_like_any_field(name, types):
    """'"params": [ <field>, … ]' — a parameter is a field node, one per shape."""
    document = signature_of(_every_shape).to_dict()
    param = _named(document["params"], name)

    assert [option["type"] for option in param["shape"]] == types


def test_a_signature_still_defines_the_structs_and_enums_its_parameters_reach():
    """A parameter points at a definition exactly as a field does; only the signature itself has no id."""
    document = signature_of(_every_shape).to_dict()

    assert document["defs"]["structs"]["_Inner"]["name"] == "_Inner"
    assert document["defs"]["enums"]["_Role"]["members"] == ["ADMIN", "USER"]
    assert _named(document["params"], "inner")["shape"][0]["ref"] == "_Inner"
    assert _named(document["params"], "role")["shape"][0]["ref"] == "_Role"


def test_a_signature_parameter_default_is_written_like_a_field_default():
    """'"params": [ <field>, … ]' — same node, same rules for `default`."""
    params = signature_of(_upload).to_dict()["params"]

    assert "default" not in _named(params, "path")
    assert _named(params, "when")["default"] == "2024-01-01"
    assert _named(params, "role")["default"] == "USER"

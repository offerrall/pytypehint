"""Release hardening, agent A: promises with no test behind them.

Every test here pins a sentence the documentation states as an absolute and that
no other test in the suite exercises. Where a sentence was false when this file
was written, the test recorded the defect until the fix landed; every one of them
passes now, so each sentence is an absolute the suite holds the core to.
"""
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, fields as dc_fields, make_dataclass
from datetime import date, time
from enum import Enum
from typing import Annotated

import pytest

import pytypehint
from pytypehint import (
    Choices, Description, Extra, FileHint, IsPassword, Label, Max, Min,
    MultipleOf, OptionalToggle, Pattern, Placeholder, Rows, SchemaTypeError,
    SchemaValueError, Slider, Step, signature_of, struct_of,
)
from pytypehint.shapes import (
    Bool, Date, EnumShape, Float, Int, List, NoneShape, Str, Time,
)
from pytypehint.structure import Struct


# ---------------------------------------------------------------------------
# 1. The one determinism caveat the format admits: `python -OO`
#
# docs/contract.md, "Two guarantees":
#   "One caveat, and it belongs to the interpreter rather than to the emitter: a
#    signature's `doc` is the function's `__doc__`, and `python -OO` discards
#    every docstring, so under that flag the key is absent. Documents are
#    comparable across runs of the same interpreter configuration, not across a
#    change of it."
# CHANGELOG 1.0.0 repeats it: "`python -OO` discards docstrings, so a
# signature's `doc` key disappears under that flag."
#
# Nothing else in the suite runs an optimized interpreter, so the caveat was
# documentation only. These run one.
# ---------------------------------------------------------------------------

_DOC_PROBE = """
import json
from pytypehint import signature_of


def upload(name: str):
    "Upload a document."


document = signature_of(upload).to_dict()
print(json.dumps({"keys": list(document), "doc": document.get("doc"),
                  "text": json.dumps(document)}))
"""


def _probe(*flags):
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    finished = subprocess.run([sys.executable, *flags, "-c", _DOC_PROBE],
                              capture_output=True, text=True, env=env, check=True)
    return json.loads(finished.stdout)


@pytest.mark.parametrize("flags, present", [
    ((), True),
    (("-O",), True),
    (("-OO",), False),
], ids=["plain", "O", "OO"])
def test_the_doc_key_follows_the_interpreters_docstring_setting(flags, present):
    """'`python -OO` discards every docstring, so under that flag the key is absent'.

    `-O` keeps docstrings and must not move the key: the caveat is about `-OO`
    alone, and stating it more broadly would make the format look less stable
    than it is.
    """
    probe = _probe(*flags)

    assert ("doc" in probe["keys"]) is present
    if present:
        assert probe["doc"] == "Upload a document."


def test_dropping_doc_is_the_only_difference_an_optimized_interpreter_makes():
    """'Documents are comparable across runs of the same interpreter configuration'.

    The rest of the document is byte for byte identical, which is what makes the
    caveat a caveat rather than a hole in the determinism guarantee.
    """
    plain = json.loads(_probe()["text"])
    optimized = json.loads(_probe("-OO")["text"])

    assert plain.pop("doc") == "Upload a document."
    assert json.dumps(plain) == json.dumps(optimized)
    assert _probe("-OO")["text"] == _probe("-OO")["text"]


# ---------------------------------------------------------------------------
# 2. The one value a float node cannot canonicalize
#
# docs/contract.md, "Shape nodes":
#   "A number on a `float` node is written as a float… The one value this cannot
#    do is an integer with no float of equal magnitude, which is left as it is
#    rather than failing."
#
# There are two ways an integer can have no float of equal value, and the document
# must not paper over either. One is being outside the float range altogether:
# that names no float at all and the shape now refuses it as an atom error. The
# other is the subtle one — inside the range but not representable, because above
# 2**53 the floats thin out — and there `float()` answers with a *neighbour*
# instead of failing. Publishing the neighbour would state a bound the schema does
# not hold, so the integer is written as it is. This is the reachable case, and it
# arrives through an ordinary `Min`.
# ---------------------------------------------------------------------------

_NO_FLOAT_TWIN = 10 ** 400
_NOT_REPRESENTABLE = 2 ** 53 + 1


def _node(annotation, **default):
    cls = make_dataclass("Probe", [("x", annotation, *default.get("spec", ()))])
    document = struct_of(cls).to_dict()
    return document["defs"]["structs"][document["root"]]["fields"][0]["shape"][0]


@pytest.mark.parametrize("atom", [Min, Max, Step], ids=["min", "max", "step"])
def test_a_number_outside_the_float_range_is_an_atom_error(atom):
    with pytest.raises((TypeError, ValueError)):
        struct_of(make_dataclass("Probe", [("x", Annotated[float, atom(_NO_FLOAT_TWIN)])]))


@pytest.mark.parametrize("atom,key", [(Min, "min"), (Max, "max")])
def test_an_int_with_no_float_of_equal_value_is_left_as_it_is(atom, key):
    """'…which is left as it is rather than failing'."""
    node = _node(Annotated[float, atom(_NOT_REPRESENTABLE)])

    assert node["type"] == "float"
    # Written as it is, not as the float that merely sits nearest to it.
    assert node[key] == _NOT_REPRESENTABLE
    assert type(node[key]) is int
    assert node[key] != float(_NOT_REPRESENTABLE)
    assert json.loads(json.dumps(node))[key] == _NOT_REPRESENTABLE


def test_the_published_bound_is_the_bound_the_schema_enforces():
    """A document that named the neighbour would invite a value the core rejects."""
    cls = make_dataclass("Probe", [("x", Annotated[float, Min(_NOT_REPRESENTABLE)])])
    schema = struct_of(cls)
    published = _node(Annotated[float, Min(_NOT_REPRESENTABLE)])["min"]

    assert published == schema.fields[0].shape[0].min.value
    # The nearest float is below the real bound, so a reader that had been given it
    # would have sent a value the schema refuses.
    with pytest.raises(SchemaValueError):
        schema.build({"x": float(_NOT_REPRESENTABLE)})


def test_every_representable_number_on_a_float_node_is_written_as_a_float():
    node = _node(Annotated[float, Min(0), Max(1), Step(1), Choices(values=(0.0, 1.0))])

    assert node["type"] == "float"
    for key in ("min", "max", "step"):
        assert type(node[key]) is float, key
    assert all(type(c) is float for c in node["choices"])
    assert json.loads(json.dumps(node)) == node


def test_a_float_bound_with_no_float_twin_is_rejected_as_an_atom_error():
    with pytest.raises((TypeError, ValueError)):
        struct_of(make_dataclass("Probe", [("x", Annotated[float, Min(_NO_FLOAT_TWIN)])]))


# ---------------------------------------------------------------------------
# 3. "every atom the *author* wrote" reaches the document
#
# docs/contract.md, "What it is for":
#   "What it does carry is every atom the *author* wrote, including the notation
#    ones: `Label`, `Description`, `Placeholder`, the message on a `Pattern`, and
#    also `Rows`, `Step`, `Slider` and `IsPassword`."
#
# The suite checks each node against a hand-written expectation. This checks the
# emitter against the shape dataclasses by reflection, so a new atom field added
# to a shape and not written cannot pass unnoticed.
# ---------------------------------------------------------------------------

# shape class -> {dataclass field name: the document key it must produce}
_EMITTED = {
    Int: {"min": "min", "max": "max", "choices": "choices",
          "multiple_of": "multiple_of", "step": "step", "slider": "slider",
          "placeholder": "placeholder", "_extras": "extras"},
    Float: {"min": "min", "max": "max", "choices": "choices", "step": "step",
            "slider": "slider", "placeholder": "placeholder", "_extras": "extras"},
    Str: {"min": "min_length", "max": "max_length", "choices": "choices",
          "pattern": "pattern", "file_hint": "file_hint",
          "is_password": "is_password", "rows": "rows",
          "placeholder": "placeholder", "_extras": "extras"},
    Date: {"min": "min", "max": "max", "choices": "choices",
           "placeholder": "placeholder", "_extras": "extras"},
    Time: {"min": "min", "max": "max", "choices": "choices",
           "placeholder": "placeholder", "_extras": "extras"},
    List: {"min": "min_items", "max": "max_items", "item": "item",
           "_extras": "extras"},
    Bool: {"_extras": "extras"},
    NoneShape: {"_extras": "extras"},
    EnumShape: {"cls": "ref", "_extras": "extras"},
    Struct: {"cls": "ref"},
}
# Not atoms and deliberately absent: the compiled pattern is implementation
# (contract.md, "What never appears"), and a Struct's fields live in `defs`.
_NOT_EMITTED = {(Str, "_compiled"), (Struct, "fields")}


@pytest.mark.parametrize("shape_cls", list(_EMITTED), ids=lambda c: c.__name__)
def test_the_emitter_map_still_covers_every_field_of_every_shape(shape_cls):
    """A new atom field on a shape must be given a document key deliberately."""
    declared = {f.name for f in dc_fields(shape_cls)
                if (shape_cls, f.name) not in _NOT_EMITTED}

    assert declared == set(_EMITTED[shape_cls])


class _Role(Enum):
    ADMIN = "admin"
    USER = "user"


_FULLY_ANNOTATED = {
    "int": (Annotated[int, Min(0, exclusive=True), Max(10, exclusive=True),
                      MultipleOf(2), Step(2), Slider(show_value=True),
                      Placeholder("p"), Choices(values=(2, 4)), Extra("a.b", "c")],
            {"min", "exclusive_min", "max", "exclusive_max", "multiple_of", "step",
             "slider", "placeholder", "choices", "extras"}),
    "float": (Annotated[float, Min(0.0, exclusive=True), Max(1.0, exclusive=True),
                        Step(0.5), Slider(show_value=False), Placeholder("p"),
                        Choices(values=(0.5,)), Extra("a.b", "c")],
              {"min", "exclusive_min", "max", "exclusive_max", "step", "slider",
               "placeholder", "choices", "extras"}),
    "str": (Annotated[str, Min(1), Max(4), Pattern(r"a+", message="m"), IsPassword(),
                      Rows(3), Placeholder("p"), Choices(values=("a", "aa")),
                      Extra("a.b", "c")],
            {"min_length", "max_length", "pattern", "pattern_message", "is_password",
             "rows", "placeholder", "choices", "extras"}),
    "date": (Annotated[date, Min(date(2000, 1, 1), exclusive=True),
                       Max(date(2030, 1, 1), exclusive=True), Placeholder("p"),
                       Choices(values=(date(2026, 1, 1),)), Extra("a.b", "c")],
             {"min", "exclusive_min", "max", "exclusive_max", "placeholder",
              "choices", "extras"}),
    "time": (Annotated[time, Min(time(1, 0), exclusive=True),
                       Max(time(23, 0), exclusive=True), Placeholder("p"),
                       Choices(values=(time(2, 0),)), Extra("a.b", "c")],
             {"min", "exclusive_min", "max", "exclusive_max", "placeholder",
              "choices", "extras"}),
    "list": (Annotated[list[int], Min(1), Max(3), Extra("a.b", "c")],
             {"min_items", "max_items", "item", "extras"}),
    "bool": (Annotated[bool, Extra("a.b", "c")], {"extras"}),
    "enum": (Annotated[_Role, Extra("a.b", "c")], {"ref", "extras"}),
}


@pytest.mark.parametrize("kind", list(_FULLY_ANNOTATED))
def test_every_atom_a_shape_admits_lands_on_its_node_with_extras_last(kind):
    """'…every atom the *author* wrote' — and '`extras` is last on every node'."""
    annotation, keys = _FULLY_ANNOTATED[kind]

    node = _node(annotation)

    assert keys <= set(node)
    assert list(node)[0] == "type"
    assert list(node)[-1] == "extras"


def test_the_none_option_of_a_union_carries_its_extras():
    """'{"type": "none", "id": "None", "extras": {…}}' — reachable only per option."""
    cls = make_dataclass(
        "Probe", [("x", int | Annotated[None, Extra("a.b", "c")], field(default=None))])
    document = struct_of(cls).to_dict()
    shape = document["defs"]["structs"][document["root"]]["fields"][0]["shape"]

    assert shape == [{"type": "int", "id": "int"},
                     {"type": "none", "id": "None", "extras": {"a.b": "c"}}]


def test_the_file_hint_mark_writes_every_narrowing_it_carries():
    """'"file_hint": {"extensions": [".pdf"], "min_size": 0, "max_size": 1048576}'.

    The sizes are stated, not checked, so the default below names a file that need
    not exist: what reaches the document is the atom the author wrote.
    """
    mark = FileHint(extensions=(".pdf",), min_size=1, max_size=99)
    cls = make_dataclass("Probe", [("x", Annotated[str, mark, Extra("a.b", "c")],
                                    field(default="nowhere/f.pdf"))])
    document = struct_of(cls).to_dict()
    node = document["defs"]["structs"][document["root"]]["fields"][0]["shape"][0]

    assert node["file_hint"] == {"extensions": [".pdf"], "min_size": 1,
                                 "max_size": 99}
    assert list(node)[-1] == "extras"


def test_a_field_node_writes_its_keys_in_the_documented_order():
    """docs/contract.md, "Fields": name, label, description, optional_toggle, default, shape."""
    cls = make_dataclass("Probe", [(
        "x", Annotated[int | None, Label("L"), Description("D"), OptionalToggle(False)],
        field(default=None))])
    document = struct_of(cls).to_dict()
    node = document["defs"]["structs"][document["root"]]["fields"][0]

    assert list(node) == ["name", "label", "description", "optional_toggle",
                          "default", "shape"]


# ---------------------------------------------------------------------------
# 4. Where the freshness promise ends
#
# docs/decode.md, "Fresh trees", states the boundary:
#   "The promise is about `dict` and `list` exactly, which is all a portable tree
#    has. Everything else is passed along as it is."
#
# The CHANGELOG originally claimed it without that boundary — "no dict or list in
# the result is an object from the input, at any depth" — which these two tests
# falsified; it now states the bounded promise, and they pin it. The first shows
# the promise holds for every portable tree; the second shows exactly where it
# stops, which is the side of the line a caller can reach by accident.
# ---------------------------------------------------------------------------

class _Status(Enum):
    OPEN = "open"


@dataclass
class _Nested:
    when: date
    tags: list[str]


@dataclass
class _Tree:
    n: int
    ratio: float
    at: time
    who: _Status
    inner: _Nested
    rows: list[list[str]]
    either: list[str] | list[int]
    unknownable: str


def _containers(tree):
    if type(tree) is dict:
        yield tree
        for value in tree.values():
            yield from _containers(value)
    elif type(tree) is list:
        yield tree
        for value in tree:
            yield from _containers(value)


def test_decode_shares_no_dict_or_list_with_a_portable_input_at_any_depth():
    """'no dict or list in the result is an object from the input, at any depth'."""
    wire = {"n": 1, "ratio": 3, "at": "14:30", "who": "OPEN",
            "inner": {"when": "2026-08-08", "tags": ["a", "b"]},
            "rows": [["x"], ["y"]],
            "either": {"$type": "list[str]", "$value": ["a"]},
            "unknownable": "2026-08-08",
            "surplus": {"kept": [1, {"deep": "2026-08-08"}]}}
    schema = struct_of(_Tree)
    before = json.dumps(wire, sort_keys=True)

    decoded = schema.decode(wire)

    given = {id(c) for c in _containers(wire)}
    assert not [c for c in _containers(decoded) if id(c) in given]
    assert json.dumps(wire, sort_keys=True) == before
    # and the tree really was decoded, not merely copied
    assert decoded["inner"]["when"] == date(2026, 8, 8)
    assert decoded["at"] == time(14, 30) and decoded["who"] is _Status.OPEN
    assert decoded["ratio"] == 3.0 and type(decoded["ratio"]) is float
    assert decoded["unknownable"] == "2026-08-08"
    assert decoded["either"] == {"$type": "list[str]", "$value": ["a"]}


@pytest.mark.parametrize("carried", [{"a": 1}, [1, 2]], ids=["dict", "list"])
def test_the_freshness_promise_covers_only_what_a_portable_tree_can_carry(carried):
    """'The promise is about `dict` and `list` exactly… Everything else is passed
    along as it is — right for the strings and numbers a portable tree is made of,
    and it means anything that had no business being there comes back out as the
    same object rather than a copy.'

    A tuple is not portable, so decode hands it back rather than descending into
    it, and a container reachable through it survives into the result. This is
    decode.md's rule working as written, and it is the counterexample that made
    the CHANGELOG drop its unqualified "at any depth".
    """
    schema = struct_of(make_dataclass("Probe", [("x", int)]))

    decoded = schema.decode({"x": (carried,)})

    assert decoded["x"][0] is carried


# ---------------------------------------------------------------------------
# 5. Two options of one field that answer to one identity
#
# docs/restrictions.md, "Duplicate discriminator name":
#   "A dataclass and an enum that share a class name sit in different namespaces
#    and never compete for one discriminator, so that pair stays admissible."
# docs/contract.md, "Shape nodes", states the general rule:
#   "An `id` is unique within its discriminator's namespace… It is not unique
#    across the two… Index options by position; read `id` only to fill a
#    discriminator."
#
# The pair restrictions.md names is tested elsewhere. The general case — a
# dataclass whose class name is a *scalar* identity — is not, and it is the one
# that makes "index by position" load-bearing rather than advisory.
# ---------------------------------------------------------------------------

@dataclass
class _NamedLikeAScalar:
    n: int = 0


_NamedLikeAScalar.__name__ = "str"
_NamedLikeAScalar.__qualname__ = "str"


def test_a_dataclass_named_like_a_scalar_shares_an_id_and_stays_admissible():
    """The two namespaces really are separate: one id, two reachable options."""
    cls = make_dataclass("Probe", [("x", str | _NamedLikeAScalar, field(default="hi"))])
    schema = struct_of(cls)

    assert [option.option_id() for option in schema.fields[0].shape] == ["str", "str"]

    document = schema.to_dict()
    shape = document["defs"]["structs"][document["root"]]["fields"][0]["shape"]
    assert [node["id"] for node in shape] == ["str", "str"]
    assert [node["type"] for node in shape] == ["str", "struct"]

    # Both options are reachable, so neither id is dead: the value's own runtime
    # type routes it and no discriminator is consulted.
    assert schema.build({"x": "text"}).x == "text"
    assert type(schema.build({"x": {"n": 1}}).x) is _NamedLikeAScalar
    # A bare portable string reads as the `str`, and the dataclass as an object.
    assert schema.build(schema.decode({"x": "text"})).x == "text"


# ---------------------------------------------------------------------------
# 6. The public surface of a 1.0.0
#
# README, "Public API": "Everything public is exported from `pytypehint`."
# CHANGELOG 1.0.0: "the public surface grows by no new names: both are methods on
# the schema that was already there."
# docs/philosophy.md, "Keep the public surface small": "publishing implementation
# machinery creates permanent compatibility obligations."
#
# The suite ties __all__ to the README in both directions. Nothing ties it to the
# release it claims not to have changed, which is the claim a 1.0.0 freezes.
# ---------------------------------------------------------------------------

# `git show 218b50b:src/pytypehint/__init__.py` — the 0.0.7 __all__, in order, with
# the one rename 1.0.0 makes applied in the same slot; the CHANGELOG records which
# name moved and why. A rename is not growth, which is what the claim below is
# about, but it is the kind of change a 1.0.0 makes deliberately rather than by
# drift, so the list is written out and compared rather than derived.
_FROZEN_SURFACE = [
    "struct_of", "signature_of",
    "Min", "Max", "Choices", "MultipleOf", "Pattern", "FileHint",
    "Label", "Description", "Placeholder", "Step", "Slider", "IsPassword",
    "Rows", "Extra", "OptionalToggle",
    "SchemaTypeError", "SchemaValueError",
    "Struct", "Field", "Signature",
    "Shape", "Int", "Float", "Str", "Bool", "Date", "Time", "List",
    "NoneShape", "EnumShape",
    "MISSING",
]


def test_the_public_surface_grows_by_no_new_names():
    """'the public surface grows by no new names' — order included, so a diff of
    the module reads as a diff of the contract."""
    assert pytypehint.__all__ == _FROZEN_SURFACE


def test_the_two_new_operations_are_methods_on_both_compiled_schemas():
    """'The four operations are methods on the compiled schema, not separate exports'."""
    for name in ("to_dict", "decode", "resolve", "build"):
        assert name not in pytypehint.__all__
        assert not hasattr(pytypehint, name)
        assert callable(getattr(pytypehint.Struct, name))
        assert callable(getattr(pytypehint.Signature, name))


def test_no_module_level_name_escapes_all_by_accident():
    """Anything public and not in `__all__` is an accidental export."""
    escaped = sorted(name for name, value in vars(pytypehint).items()
                     if not name.startswith("_")
                     and name not in pytypehint.__all__
                     and getattr(value, "__class__", None).__name__ != "module")

    assert escaped == []


def test_the_version_is_the_one_this_release_claims():
    assert pytypehint.__version__ == "1.0.0"
    assert "__version__" not in pytypehint.__all__


# ---------------------------------------------------------------------------
# 7. "Everything a sender needs is derivable from the document"
#
# docs/contract.md, "Reading the wire from the document":
#   "a `struct` option in a slot with two or more `struct` options — send the
#    object with `"$type": <name>` inside it; any other option in a slot where two
#    or more options share a portable spelling — send `{"$type": <id>, "$value":
#    <portable>}`; otherwise — send the bare portable value."
#
# The rule is property-tested over unions of one kind each. The slots it is
# easiest to get wrong are the mixed ones — a struct beside two lists, a lone
# struct that must *not* be named — so the rule is implemented here from the
# document alone and run against those.
# ---------------------------------------------------------------------------

class _Grade(Enum):
    HIGH = "high"


@dataclass
class _Cash:
    n: int = 0


@dataclass
class _Card:
    n: int = 0


@dataclass
class _Mixed:
    number: int | float
    text: str | date
    temporal: date | time
    lists: list[str] | list[int]
    structs: _Cash | _Card
    lone: _Cash
    lists_and_a_struct: list[str] | list[int] | _Cash
    plain: int
    enum_and_text: _Grade | str
    optional: int | None


_NUMBER = {"int", "float"}
_STRING = {"str", "date", "time", "enum"}


def _spelling(node):
    if node["type"] in _NUMBER:
        return "number"
    if node["type"] in _STRING:
        return "string"
    return node["type"]


def _send(document, shape, index, payload):
    """contract.md's three-line rule, implemented against the document only."""
    node = shape[index]
    if node["type"] == "struct":
        if sum(1 for other in shape if other["type"] == "struct") > 1:
            return {"$type": document["defs"]["structs"][node["ref"]]["name"], **payload}
        return payload
    if [_spelling(other) for other in shape].count(_spelling(node)) > 1:
        return {"$type": node["id"], "$value": payload}
    return payload


_WIRE = {
    "number": [(0, 1, 1), (1, 1.0, 1.0)],
    "text": [(0, "t", "t"), (1, "2026-08-08", date(2026, 8, 8))],
    "temporal": [(0, "2026-08-08", date(2026, 8, 8)), (1, "14:30:00", time(14, 30))],
    "lists": [(0, ["a"], ["a"]), (1, [1], [1])],
    "structs": [(0, {"n": 1}, _Cash(n=1)), (1, {"n": 2}, _Card(n=2))],
    "lone": [(0, {"n": 3}, _Cash(n=3))],
    "lists_and_a_struct": [(0, ["a"], ["a"]), (1, [1], [1]), (2, {"n": 4}, _Cash(n=4))],
    "plain": [(0, 7, 7)],
    "enum_and_text": [(0, "HIGH", _Grade.HIGH), (1, "plain", "plain")],
    "optional": [(0, 5, 5), (1, None, None)],
}


def _baseline(document, shape_by_name):
    return {name: _send(document, shape_by_name[name], *options[0][:2])
            for name, options in _WIRE.items()}


@pytest.mark.parametrize("name", list(_WIRE))
def test_the_documented_sender_rule_reaches_build_for_every_option_of_a_slot(name):
    """'The named spelling always works' — including in slots that mix kinds."""
    schema = struct_of(_Mixed)
    document = schema.to_dict()
    shape_by_name = {f["name"]: f["shape"]
                     for f in document["defs"]["structs"][document["root"]]["fields"]}

    for index, portable, expected in _WIRE[name]:
        data = _baseline(document, shape_by_name)
        data[name] = _send(document, shape_by_name[name], index, portable)
        # The document has to survive the transport it exists for.
        data = json.loads(json.dumps(data))

        got = getattr(schema.build(schema.decode(data)), name)

        assert got == expected and type(got) is type(expected)


def test_a_lone_struct_option_is_sent_bare_and_a_named_one_is_rejected():
    """'a `struct` option in a slot with two or more `struct` options' — and only there."""
    schema = struct_of(_Mixed)
    document = schema.to_dict()
    shape_by_name = {f["name"]: f["shape"]
                     for f in document["defs"]["structs"][document["root"]]["fields"]}
    data = _baseline(document, shape_by_name)

    assert data["lone"] == {"n": 3}
    assert data["structs"] == {"$type": "_Cash", "n": 1}
    assert data["lists_and_a_struct"] == {"$type": "list[str]", "$value": ["a"]}

    data["lone"] = {"$type": "_Cash", "n": 3}
    with pytest.raises(SchemaTypeError, match=r"lone: unexpected key\(s\): \$type"):
        schema.build(schema.decode(data))


# ---------------------------------------------------------------------------
# 8. decode is total, and to_dict never raises, over a hostile matrix
#
# CHANGELOG 1.0.0: "`decode` is total on portable trees: it returns a value for
# every input and raises nothing but `RecursionError`" and "It never raises on a
# schema the core accepted."
#
# The suite covers these case by case. This is the crossed matrix, which is what
# "total" claims.
# ---------------------------------------------------------------------------

@dataclass
class _Deep:
    a: int
    b: float
    c: str
    d: bool
    e: date
    f: time
    g: _Status
    h: int | None
    i: list[int]
    j: list[str | date]
    k: int | float
    m: str | date
    n: date | time
    o: list[str] | list[int]
    p: _Cash | _Card
    q: _Nested


_HOSTILE = [
    None, True, False, 0, 3, 3.0, 3.5, 10 ** 400, float("1e308"),
    "", "3", "true", "null", "2026-08-08", "2026-02-31", "20260808",
    "14:30", "24:00", "99:99", "10:00:00.5", "10:00:00+02:00", "OPEN",
    "list[str]", "int", "date", "_Cash",
    [], [1], ["a"], [None], [[1]], [{"n": 1}],
    {}, {"n": 1}, {"$type": "date"}, {"$value": 1},
    {"$type": "date", "$value": "2026-08-08"},
    {"$type": "date", "$value": "nonsense"},
    {"$type": "list[str]", "$value": ["a"]},
    {"$type": "list[str]", "$value": "a"},
    {"$type": 1, "$value": 1}, {"$type": "nope", "$value": 1},
    {"$type": "date", "$value": "2026-08-08", "surplus": 1},
    {"$type": "int", "$value": {"$type": "int", "$value": 1}},
    {1: "int key"}, {(1, 2): "tuple key"}, {True: "bool key"},
    ("tuple",), b"bytes", frozenset({1}), range(3),
    float("nan"), float("inf"), Ellipsis, print, _Cash(), _Status.OPEN,
    date(2026, 8, 8), time(1, 2), "٢٠٢٦-٠٨-٠٨", "２０２６-０８-０８",
]

_FIELDS = [f.name for f in dc_fields(_Deep)]


@pytest.mark.parametrize("name", _FIELDS)
def test_decode_returns_a_value_for_every_hostile_input_in_every_slot(name):
    """'it returns a value for every input and raises nothing but RecursionError'."""
    schema = struct_of(_Deep)

    for value in _HOSTILE:
        for data in ({name: value}, {name: [value]}, value):
            try:
                schema.decode(data)
            except RecursionError:
                pass


@pytest.mark.parametrize("name", _FIELDS)
def test_resolve_and_build_raise_only_the_two_schema_errors(name):
    """docs/philosophy.md: 'a schema error carries one coordinate and one reason'."""
    schema = struct_of(_Deep)

    for value in _HOSTILE:
        for data in ({name: value}, value):
            for operation in (schema.resolve, schema.build):
                try:
                    operation(data)
                except (SchemaTypeError, SchemaValueError, RecursionError):
                    pass


def test_to_dict_never_raises_and_is_deterministic_for_every_admitted_shape():
    """'It never raises on a schema the core accepted' + 'byte for byte'."""
    def action(v: _Deep, w: list[_Nested], x: Annotated[int, Min(0)] = 1):
        """d"""

    for schema in (struct_of(_Deep), struct_of(_Nested), struct_of(_Tree),
                   struct_of(_Mixed), signature_of(action)):
        first, second = schema.to_dict(), schema.to_dict()

        assert first is not second
        assert json.dumps(first) == json.dumps(second)
        assert json.dumps(first) == json.dumps(json.loads(json.dumps(first)))


# ---------------------------------------------------------------------------
# 9. `extras` is a snapshot, not a read-only view
#
# README: "The `extras` property returns a fresh `dict[str, str]` on every
# access, so callers may modify that snapshot without changing the shape."
# docs/atoms.md says the opposite word: "exposes them as a read-only `extras`
# dict built on access".
#
# The behaviour is the README's. Pinning it keeps the wording from being
# "corrected" towards a MappingProxy that would break the documented use.
# ---------------------------------------------------------------------------

def test_the_extras_snapshot_is_a_plain_mutable_dict_detached_from_the_shape():
    """'callers may modify that snapshot without changing the shape'."""
    cls = make_dataclass("Probe", [("x", Annotated[int, Extra("a.x", "1")])])
    shape = struct_of(cls).fields[0].shape[0]

    snapshot = shape.extras
    assert type(snapshot) is dict
    snapshot["a.x"] = "changed"
    snapshot["b.added"] = ""
    del snapshot["b.added"]

    assert shape.extras == {"a.x": "1"}
    assert shape.extras is not shape.extras

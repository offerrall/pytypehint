"""The definition graph, determinism and defaults of the portable document.

Everything here freezes what docs/contract.md promises about the *shape of the
document as a whole*, rather than about any single atom:

* "Definitions" — a struct and an enum are always a reference, never inlined;
  ids are handles made unique inside one document, names are contract;
  structs and enums have separate tables.
* "Two guarantees" — equal definitions produce equal documents byte for byte,
  across processes and hash seeds, and every call returns a tree the caller owns
  completely.
* "Defaults" / "Reading the wire from the document" — a default is written in
  decode's own portable language, wrapped exactly where two options share a
  portable spelling, so a default read out of the document is valid input to
  `decode`.

Per-shape and per-atom coverage, and the "what never appears" leak sweep, live
in their own files and are not repeated here.
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

from pytypehint import Extra, List, Struct, signature_of, struct_of


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class _Role(Enum):
    ADMIN = "a"
    USER = "u"


class _Status(Enum):
    OPEN = 1
    CLOSED = 2


class _Palette(Enum):
    """Definition order is not alphabetical, and CRIMSON is an alias of RED."""

    ZULU = 1
    ALPHA = 2
    MIKE = 3
    CRIMSON = 1


class _Crossed(Enum):
    """Each member's value is another member's name — names must win."""

    RED = "BLUE"
    BLUE = "RED"


class _Unportable(Enum):
    """No member value survives a portable tree; only names are published."""

    PAIR = (1, 2)
    THING = object()
    BAG = frozenset({1, 2})


# ---------------------------------------------------------------------------
# Recursive and shared dataclasses (module level, so forward refs resolve)
# ---------------------------------------------------------------------------

@dataclass
class _Node:
    value: int = 0
    parent: "_Node | None" = None
    children: "list[_Node]" = field(default_factory=list)


@dataclass
class _MutualA:
    b: "_MutualB | None" = None


@dataclass
class _MutualB:
    a: "_MutualA | None" = None


@dataclass
class _HopA:
    b: "_HopB | None" = None


@dataclass
class _HopB:
    c: "_HopC | None" = None


@dataclass
class _HopC:
    a: "_HopA | None" = None


@dataclass
class _Leaf:
    n: int = 0


@dataclass
class _Twice:
    left: _Leaf = field(default_factory=_Leaf)
    right: _Leaf = field(default_factory=_Leaf)


@dataclass
class _ManyWays:
    """One dataclass reached through a field, a union, a list and a nested struct."""

    direct: _Leaf = field(default_factory=_Leaf)
    optional: _Leaf | None = None
    many: list[_Leaf] = field(default_factory=list)
    through: _Twice = field(default_factory=_Twice)


# ---------------------------------------------------------------------------
# Dataclasses carrying defaults
# ---------------------------------------------------------------------------

@dataclass
class _Inner:
    n: int = 1
    when: date = date(2024, 1, 1)


@dataclass
class _Shipped:
    on: date = date(2024, 1, 1)


@dataclass
class _Cancelled:
    reason: str = "none given"


@dataclass
class _PlainDefaults:
    an_int: int = 7
    a_float: float = 1.5
    a_whole_float: float = 2.0
    a_str: str = "hi"
    a_true: bool = True
    a_false: bool = False
    a_none: int | None = None
    a_date: date = date(2024, 6, 1)
    a_time: time = time(9, 30, 15)
    an_enum_member: _Role = _Role.USER
    a_list_of_scalars: list[str] = field(default_factory=lambda: ["a", "b"])
    a_list_of_dates: list[date] = field(
        default_factory=lambda: [date(2020, 1, 1), date(2021, 2, 3)])
    a_nested_list: list[list[int]] = field(default_factory=lambda: [[1, 2], [3]])
    a_list_of_enum_members: list[_Role] = field(
        default_factory=lambda: [_Role.ADMIN, _Role.USER])
    an_empty_list: list[int] = field(default_factory=list)
    a_nested_dataclass: _Inner = field(default_factory=_Inner)
    a_shipped_in_a_union: _Shipped | _Cancelled = field(default_factory=_Shipped)
    a_cancelled_in_a_union: _Shipped | _Cancelled = field(default_factory=_Cancelled)


@dataclass
class _AmbiguousDefaults:
    """Every field here holds two options that share one portable spelling."""

    str_or_date_with_a_date: str | date = date(2024, 6, 1)
    str_or_date_with_a_str: str | date = "2024-06-01"
    int_or_float_with_an_int: int | float = 10
    int_or_float_with_a_float: int | float = 1.5
    int_or_float_with_a_whole_float: int | float = 2.0
    date_or_time_with_a_date: date | time = date(2024, 6, 1)
    date_or_time_with_a_time: date | time = time(9, 30)
    enum_or_str_with_a_member: _Role | str = _Role.ADMIN
    enum_or_str_with_a_str: _Role | str = "ADMIN"
    enum_or_enum_with_a_role: _Role | _Status = _Role.USER
    enum_or_enum_with_a_status: _Role | _Status = _Status.OPEN
    list_or_list_with_strs: list[str] | list[int] = field(default_factory=lambda: ["a"])
    list_or_list_with_ints: list[str] | list[int] = field(default_factory=lambda: [1])


@dataclass
class _FactoryDefaults:
    """The same ground, reached through `default_factory` instead of `default`."""

    an_int: int = field(default_factory=lambda: 7)
    a_date: date = field(default_factory=lambda: date(2024, 6, 1))
    a_time: time = field(default_factory=lambda: time(9, 30, 15))
    an_enum_member: _Role = field(default_factory=lambda: _Role.USER)
    a_list_of_scalars: list[str] = field(default_factory=lambda: ["a", "b"])
    a_list_of_dates: list[date] = field(
        default_factory=lambda: [date(2020, 1, 1)])
    a_nested_list: list[list[int]] = field(default_factory=lambda: [[1, 2], [3]])
    a_nested_dataclass: _Inner = field(default_factory=_Inner)
    a_dataclass_in_a_union: _Shipped | _Cancelled = field(default_factory=_Cancelled)
    an_ambiguous_date: str | date = field(default_factory=lambda: date(2024, 6, 1))
    an_ambiguous_int: int | float = field(default_factory=lambda: 10)


@dataclass
class _InnerAmbiguous:
    """A dataclass whose own fields need the wrapper, used as someone's default."""

    when: str | date = date(2024, 6, 1)
    role: _Role | str = _Role.ADMIN


@dataclass
class _NestedAmbiguousDefaults:
    """The ambiguity is one level down: inside a list item slot, or inside a
    nested dataclass. contract.md states the rule per *slot*, and a list's `item`
    is "the set of options one element may take"."""

    list_of_str_or_date: list[str | date] = field(
        default_factory=lambda: [date(2024, 6, 1)])
    list_of_enum_or_str: list[_Role | str] = field(
        default_factory=lambda: [_Role.ADMIN])
    list_of_date_or_time: list[date | time] = field(
        default_factory=lambda: [time(9, 30)])
    list_of_enum_or_enum: list[_Role | _Status] = field(
        default_factory=lambda: [_Status.OPEN])
    list_of_int_or_float: list[int | float] = field(
        default_factory=lambda: [2.0])
    grid_of_str_or_date: list[list[str | date]] = field(
        default_factory=lambda: [[date(2020, 1, 1)]])
    nested_dataclass: _InnerAmbiguous = field(default_factory=_InnerAmbiguous)


@dataclass
class _PartlyDefaulted:
    without_default: int
    with_default: int = 3
    without_default_too: str = "x"


# ---------------------------------------------------------------------------
# A struct and an enum wearing one class name
# ---------------------------------------------------------------------------

class _Twin(Enum):
    LEFT = 1
    RIGHT = 2


@dataclass
class _TwinStruct:
    n: int = 0


# The struct now answers to the enum's class name — the pair the core admits on
# purpose, because structs and enums have separate discriminators.
_TwinStruct.__name__ = "_Twin"


@dataclass
class _NamesakeHolder:
    an_enum: _Twin = _Twin.LEFT
    a_struct: _TwinStruct = field(default_factory=_TwinStruct)


# ---------------------------------------------------------------------------
# Factories for homonym classes: same __name__, __module__ and __qualname__
# ---------------------------------------------------------------------------

def _make_point_class():
    @dataclass
    class P:
        v: int = 0

    return P


def _make_flag_enum():
    class F(Enum):
        ON = 1
        OFF = 2

    return F


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _definition(document: dict, ident: str) -> dict:
    return document["defs"]["structs"][ident]


def _field_node(document: dict, ident: str, name: str) -> dict:
    for node in _definition(document, ident)["fields"]:
        if node["name"] == name:
            return node
    raise AssertionError(f"no field {name!r} in definition {ident!r}")


def _document_default(cls, name: str):
    """The portable default the document publishes for one field."""
    return _field_node(struct_of(cls).to_dict(), cls.__name__, name)["default"]


def _compiled_default(cls, name: str):
    """The certified Python default the schema holds for the same field."""
    for f in struct_of(cls).fields:
        if f.name == name:
            return f.default
    raise AssertionError(f"no field {name!r} on {cls.__name__}")


def _round_trip(cls, name: str):
    """`decode` the document's default, then `build` — the pipeline decode.md fixes."""
    schema = struct_of(cls)
    written = _field_node(schema.to_dict(), cls.__name__, name)["default"]
    return getattr(schema.build(schema.decode({name: written})), name)


def _shape_nodes(document: dict):
    """Every shape node in the document, reached only through `shape` and `item`."""
    def walk(slot):
        for node in slot:
            yield node
            if node["type"] == "list":
                yield from walk(node["item"])

    for definition in document["defs"]["structs"].values():
        for f in definition["fields"]:
            yield from walk(f["shape"])
    for param in document.get("params", ()):
        yield from walk(param["shape"])


def _container_ids(tree, acc=None) -> set:
    """`id()` of every dict and list in a tree, so two trees can be compared."""
    if acc is None:
        acc = set()
    if type(tree) is dict:
        acc.add(id(tree))
        for value in tree.values():
            _container_ids(value, acc)
    elif type(tree) is list:
        acc.add(id(tree))
        for value in tree:
            _container_ids(value, acc)
    return acc


def _count_nodes(tree) -> int:
    if type(tree) is dict:
        return 1 + sum(_count_nodes(v) for v in tree.values())
    if type(tree) is list:
        return 1 + sum(_count_nodes(v) for v in tree)
    return 1


def _every_string(tree):
    if type(tree) is dict:
        for key, value in tree.items():
            yield key
            yield from _every_string(value)
    elif type(tree) is list:
        for value in tree:
            yield from _every_string(value)
    elif type(tree) is str:
        yield tree


def _dense_dag_class(levels: int) -> type:
    """`L0`, then `Ln(x: L(n-1), y: L(n-1))` — 2**n paths, `levels + 1` classes."""
    made = [make_dataclass("L0", [("n", int)])]
    for i in range(1, levels + 1):
        made.append(make_dataclass(f"L{i}", [("x", made[-1]), ("y", made[-1])]))
    return made[-1]


def _chain_class(length: int) -> type:
    """A straight chain `C0 <- C1 <- … <- Cn`, one reference per level."""
    made = [make_dataclass("C0", [("n", int)])]
    for i in range(1, length + 1):
        made.append(make_dataclass(f"C{i}", [("next", made[-1])]))
    return made[-1]


# ---------------------------------------------------------------------------
# Always a reference, never inlined
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls", [_Node, _MutualA, _Twice, _ManyWays, _PlainDefaults],
                         ids=["node", "mutual", "twice", "many_ways", "plain_defaults"])
def test_every_struct_option_is_written_as_a_reference(cls):
    """contract.md, Definitions: "Always a reference, never inlined"."""
    for node in _shape_nodes(struct_of(cls).to_dict()):
        if node["type"] == "struct":
            assert "ref" in node
            assert "fields" not in node
            assert "name" not in node


@pytest.mark.parametrize("cls", [_PlainDefaults, _AmbiguousDefaults, _NamesakeHolder],
                         ids=["plain_defaults", "ambiguous_defaults", "namesakes"])
def test_every_enum_option_is_written_as_a_reference(cls):
    """contract.md, Definitions: an enum occurrence carries `ref`, never members."""
    for node in _shape_nodes(struct_of(cls).to_dict()):
        if node["type"] == "enum":
            assert "ref" in node
            assert "members" not in node
            assert "name" not in node


def test_a_struct_node_carries_nothing_but_type_id_and_ref():
    """contract.md: "A `Struct` node never has extras"."""
    document = struct_of(_Node).to_dict()
    structs = [n for n in _shape_nodes(document) if n["type"] == "struct"]
    assert structs
    for node in structs:
        assert set(node) <= {"type", "id", "ref"}


@pytest.mark.parametrize("cls,expected", [
    pytest.param(_Node, 1, id="self_recursive"),
    pytest.param(_Twice, 2, id="one_shared_leaf"),
    pytest.param(_ManyWays, 3, id="three_distinct_classes"),
    pytest.param(_MutualA, 2, id="mutual_pair"),
    pytest.param(_HopA, 3, id="three_hop_cycle"),
])
def test_definition_count_equals_the_number_of_distinct_classes(cls, expected):
    """contract.md, Definitions: "A struct is written once"."""
    document = struct_of(cls).to_dict()
    assert len(document["defs"]["structs"]) == expected


def test_every_reference_resolves_inside_the_document():
    """A `ref` is a handle into this document and must always land somewhere."""
    document = struct_of(_ManyWays).to_dict()
    for node in _shape_nodes(document):
        if node["type"] == "struct":
            assert node["ref"] in document["defs"]["structs"]
        elif node["type"] == "enum":
            assert node["ref"] in document["defs"]["enums"]


def test_the_root_is_an_id_in_the_struct_table():
    document = struct_of(_Node).to_dict()
    assert document["root"] in document["defs"]["structs"]
    assert document["kind"] == "struct"
    assert document["v"] == 1


# ---------------------------------------------------------------------------
# Recursion terminates and stays flat
# ---------------------------------------------------------------------------

def test_self_recursion_writes_one_definition_that_points_back_at_itself():
    """contract.md: referencing "is what makes recursion terminate"."""
    document = struct_of(_Node).to_dict()
    (ident,) = document["defs"]["structs"]
    assert ident == document["root"] == "_Node"

    parent = _field_node(document, ident, "parent")
    assert {"type": "struct", "id": "_Node", "ref": ident} in parent["shape"]


def test_self_recursion_through_a_list_points_back_at_the_root():
    document = struct_of(_Node).to_dict()
    children = _field_node(document, "_Node", "children")
    (list_node,) = children["shape"]
    assert list_node["type"] == "list"
    assert list_node["item"] == [{"type": "struct", "ref": "_Node"}]


def test_mutual_recursion_writes_one_definition_per_class():
    document = struct_of(_MutualA).to_dict()
    assert list(document["defs"]["structs"]) == ["_MutualA", "_MutualB"]
    assert _field_node(document, "_MutualB", "a")["shape"][0]["ref"] == "_MutualA"


def test_three_hop_recursion_closes_the_loop_in_the_document():
    document = struct_of(_HopA).to_dict()
    assert list(document["defs"]["structs"]) == ["_HopA", "_HopB", "_HopC"]
    assert _field_node(document, "_HopC", "a")["shape"][0]["ref"] == "_HopA"


def test_a_recursive_document_stays_small():
    """One definition, not a tree of them."""
    assert _count_nodes(struct_of(_Node).to_dict()) < 100


@pytest.mark.parametrize("length", [20, 25, 40], ids=lambda n: f"chain_{n}")
def test_a_deep_chain_writes_one_definition_per_class(length):
    document = struct_of(_chain_class(length)).to_dict()
    assert len(document["defs"]["structs"]) == length + 1
    assert list(document["defs"]["structs"]) == [f"C{i}" for i in range(length, -1, -1)]


@pytest.mark.parametrize("levels", [15, 18, 20], ids=lambda n: f"dag_{n}")
def test_a_dense_dag_writes_one_definition_per_level(levels):
    """contract.md: "twenty structs … two million nodes if inlined, twenty-one if
    referenced"."""
    document = struct_of(_dense_dag_class(levels)).to_dict()
    assert len(document["defs"]["structs"]) == levels + 1


@pytest.mark.parametrize("levels", [15, 18, 20], ids=lambda n: f"dag_{n}")
def test_a_dense_dag_document_grows_with_the_classes_not_with_the_paths(levels):
    """The structural invariant behind "it terminates quickly": size is linear."""
    document = struct_of(_dense_dag_class(levels)).to_dict()
    assert _count_nodes(document) < 50 * (levels + 1)


def test_a_dense_dag_reaches_every_level_exactly_once():
    document = struct_of(_dense_dag_class(15)).to_dict()
    idents = list(document["defs"]["structs"])
    assert idents == [f"L{i}" for i in range(15, -1, -1)]
    assert len(idents) == len(set(idents))
    for i in range(15, 0, -1):
        definition = _definition(document, f"L{i}")
        assert [f["shape"][0]["ref"] for f in definition["fields"]] == [f"L{i - 1}"] * 2


# ---------------------------------------------------------------------------
# Sharing
# ---------------------------------------------------------------------------

def test_two_fields_of_one_dataclass_share_a_single_definition():
    document = struct_of(_Twice).to_dict()
    assert list(document["defs"]["structs"]) == ["_Twice", "_Leaf"]
    left = _field_node(document, "_Twice", "left")["shape"][0]
    right = _field_node(document, "_Twice", "right")["shape"][0]
    assert left["ref"] == right["ref"] == "_Leaf"


def test_struct_of_reuses_one_struct_object_for_a_shared_dataclass():
    """The document mirrors the compiled graph: one Struct, two occurrences."""
    schema = struct_of(_Twice)
    assert schema.fields[0].shape[0] is schema.fields[1].shape[0]


def test_a_dataclass_reached_many_ways_is_defined_once():
    """A field, a union arm, a list item and a nested struct — one definition,
    five occurrences, every one of them a `ref`."""
    document = struct_of(_ManyWays).to_dict()
    assert list(document["defs"]["structs"]).count("_Leaf") == 1
    refs = [n["ref"] for n in _shape_nodes(document) if n["type"] == "struct"]
    assert refs.count("_Leaf") == 5


def test_two_signature_params_of_one_dataclass_share_a_single_definition():
    def upload(first: _Leaf, second: _Leaf, count: int = 1):
        """Upload a document."""

    document = signature_of(upload).to_dict()
    assert document["kind"] == "signature"
    assert document["name"] == "upload"
    assert document["doc"] == "Upload a document."
    assert list(document["defs"]["structs"]) == ["_Leaf"]
    assert [p["shape"][0].get("ref") for p in document["params"]] == ["_Leaf", "_Leaf", None]


def test_a_recursive_dataclass_parameter_is_defined_once_in_a_signature():
    """contract.md: "A signature's parameters are written in place, because nothing
    can hold a reference to a signature" — the structs they reach still live in defs."""
    def walk(root: _Node, also: _Node | None = None):
        pass

    document = signature_of(walk).to_dict()
    assert list(document["defs"]["structs"]) == ["_Node"]
    assert [p["name"] for p in document["params"]] == ["root", "also"]
    assert document["params"][0]["shape"] == [{"type": "struct", "ref": "_Node"}]
    assert "fields" not in document["params"][0]["shape"][0]


def test_a_signature_parameter_default_round_trips_through_decode():
    """The same guarantee as a struct field: the document's default is decode input."""
    def book(when: str | date = date(2024, 6, 1), tag: str = "x"):
        pass

    schema = signature_of(book)
    document = schema.to_dict()
    written = document["params"][0]["default"]

    assert written == {"$type": "date", "$value": "2024-06-01"}
    assert schema.decode({"when": written}) == {"when": date(2024, 6, 1)}
    assert schema.params[0].default == schema.decode({"when": written})["when"]


def test_an_enum_used_by_several_fields_is_defined_once():
    document = struct_of(_AmbiguousDefaults).to_dict()
    assert list(document["defs"]["enums"]) == ["_Role", "_Status"]
    refs = [n["ref"] for n in _shape_nodes(document) if n["type"] == "enum"]
    assert refs.count("_Role") == 4


# ---------------------------------------------------------------------------
# Ids are handles; names are contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls", [_Node, _MutualA, _ManyWays, _PlainDefaults,
                                 _AmbiguousDefaults, _NamesakeHolder],
                         ids=["node", "mutual", "many_ways", "plain_defaults",
                              "ambiguous_defaults", "namesakes"])
def test_the_same_dataclass_always_produces_the_same_document(cls):
    """contract.md, Two guarantees: "Equal definitions produce equal documents"."""
    assert struct_of(cls).to_dict() == struct_of(cls).to_dict()


def test_two_homonym_classes_get_ordinal_ids_and_keep_one_name():
    """contract.md: "the id is the class name made unique within the document"."""
    first, second = _make_point_class(), _make_point_class()
    assert first is not second
    assert first.__name__ == second.__name__ == "P"
    assert first.__qualname__ == second.__qualname__
    assert first.__module__ == second.__module__

    holder = make_dataclass("Holder", [("a", first), ("b", second)])
    document = struct_of(holder).to_dict()

    assert list(document["defs"]["structs"]) == ["Holder", "P", "P#2"]
    assert _definition(document, "P")["name"] == "P"
    assert _definition(document, "P#2")["name"] == "P"


def test_three_homonym_classes_get_ordinal_ids_in_first_reach_order():
    one, two, three = _make_point_class(), _make_point_class(), _make_point_class()
    holder = make_dataclass("Holder", [("a", one), ("b", two), ("c", three)])
    document = struct_of(holder).to_dict()

    assert list(document["defs"]["structs"]) == ["Holder", "P", "P#2", "P#3"]
    assert [_definition(document, i)["name"] for i in ("P", "P#2", "P#3")] == ["P"] * 3
    assert [_field_node(document, "Holder", n)["shape"][0]["ref"]
            for n in ("a", "b", "c")] == ["P", "P#2", "P#3"]


def test_an_ordinal_id_follows_the_order_a_class_was_first_reached():
    one, two = _make_point_class(), _make_point_class()
    forwards = struct_of(make_dataclass("H", [("a", one), ("b", two)])).to_dict()
    backwards = struct_of(make_dataclass("H", [("a", two), ("b", one)])).to_dict()

    assert _field_node(forwards, "H", "a")["shape"][0]["ref"] == "P"
    assert _field_node(backwards, "H", "a")["shape"][0]["ref"] == "P"
    # Same tables, opposite classes behind the same two ids: the id is local.
    assert forwards["defs"] == backwards["defs"]


def test_an_ordinal_id_never_travels_as_a_type():
    """contract.md: "Read the `name`; use the id only to follow a `ref`"."""
    one, two = _make_point_class(), _make_point_class()
    holder = make_dataclass(
        "Holder",
        [("a", one, field(default_factory=one)), ("b", two, field(default_factory=two))])
    document = struct_of(holder).to_dict()

    assert "P#2" in document["defs"]["structs"]
    for text in _every_string(document):
        if "#" in text:
            # The only "#" in the document is an id, and an id only ever appears
            # as a table key or as the value of a `ref`.
            assert text.startswith("P#")
    refs = {n["ref"] for n in _shape_nodes(document) if n["type"] == "struct"}
    assert refs == {"P", "P#2"}


def test_the_name_not_the_id_is_what_travels_as_a_dollar_type():
    document = struct_of(_PlainDefaults).to_dict()
    written = _field_node(document, "_PlainDefaults", "a_shipped_in_a_union")["default"]
    ref = _field_node(document, "_PlainDefaults", "a_shipped_in_a_union")["shape"][0]["ref"]
    assert written["$type"] == _definition(document, ref)["name"] == "_Shipped"


def test_ids_stay_unique_even_when_a_class_name_already_wears_an_ordinal():
    """The promise is uniqueness *within the document*, not a reserved spelling."""
    def named(text):
        cls = _make_point_class()
        cls.__name__ = text
        return cls

    first, ordinal_looking, third = named("P"), named("P#2"), named("P")
    holder = make_dataclass(
        "H", [("a", first), ("b", ordinal_looking), ("c", third)])
    document = struct_of(holder).to_dict()

    idents = list(document["defs"]["structs"])
    assert len(idents) == len(set(idents)) == 4
    for node in _shape_nodes(document):
        if node["type"] == "struct":
            assert node["ref"] in document["defs"]["structs"]


def test_two_homonym_enums_get_ordinal_ids_and_keep_one_name():
    first, second = _make_flag_enum(), _make_flag_enum()
    holder = make_dataclass(
        "Holder", [("a", first, field(default=first.ON)),
                   ("b", second, field(default=second.OFF))])
    document = struct_of(holder).to_dict()

    assert list(document["defs"]["enums"]) == ["F", "F#2"]
    assert [document["defs"]["enums"][i]["name"] for i in ("F", "F#2")] == ["F", "F"]


# ---------------------------------------------------------------------------
# Separate tables
# ---------------------------------------------------------------------------

def test_a_struct_and_an_enum_of_one_class_name_sit_in_separate_tables():
    """contract.md: "the core admits that pair on purpose"."""
    document = struct_of(_NamesakeHolder).to_dict()

    assert "_Twin" in document["defs"]["structs"]
    assert "_Twin" in document["defs"]["enums"]
    assert document["defs"]["structs"]["_Twin"]["name"] == "_Twin"
    assert document["defs"]["enums"]["_Twin"]["name"] == "_Twin"
    # Neither table needed an ordinal: they never competed for one key.
    assert not any("#" in i for i in document["defs"]["structs"])
    assert not any("#" in i for i in document["defs"]["enums"])


def test_a_namesake_pair_is_told_apart_by_the_node_type():
    document = struct_of(_NamesakeHolder).to_dict()
    an_enum = _field_node(document, "_NamesakeHolder", "an_enum")["shape"][0]
    a_struct = _field_node(document, "_NamesakeHolder", "a_struct")["shape"][0]

    assert (an_enum["type"], an_enum["ref"]) == ("enum", "_Twin")
    assert (a_struct["type"], a_struct["ref"]) == ("struct", "_Twin")


@pytest.mark.parametrize("cls", [_Leaf, _Node, _PlainDefaults],
                         ids=["leaf", "node", "plain_defaults"])
def test_defs_always_carries_both_tables(cls):
    """contract.md: "`defs` is always present with both tables, even empty"."""
    document = struct_of(cls).to_dict()
    assert set(document["defs"]) == {"structs", "enums"}
    assert type(document["defs"]["enums"]) is dict


def test_a_signature_without_definitions_still_carries_both_tables():
    def plain(x: int = 0):
        pass

    document = signature_of(plain).to_dict()
    assert document["defs"] == {"structs": {}, "enums": {}}
    assert "doc" not in document


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

def test_enum_members_keep_definition_order():
    """contract.md: "canonical members, in definition order"."""
    document = struct_of(
        make_dataclass("H", [("p", _Palette, field(default=_Palette.MIKE))])).to_dict()
    assert document["defs"]["enums"]["_Palette"]["members"] == ["ZULU", "ALPHA", "MIKE"]


def test_enum_aliases_are_left_out_of_members():
    """contract.md: "Aliases are left out: an alias names a member already listed"."""
    document = struct_of(
        make_dataclass("H", [("p", _Palette, field(default=_Palette.ZULU))])).to_dict()
    members = document["defs"]["enums"]["_Palette"]["members"]
    assert "CRIMSON" not in members
    assert len(members) == len(set(members)) == 3


def test_enum_members_are_names_even_when_a_value_spells_another_name():
    document = struct_of(
        make_dataclass("H", [("c", _Crossed, field(default=_Crossed.RED))])).to_dict()
    assert document["defs"]["enums"]["_Crossed"]["members"] == ["RED", "BLUE"]
    assert _field_node(document, "H", "c")["default"] == "RED"


def test_a_definition_carries_nothing_but_a_name_and_its_members():
    document = struct_of(_AmbiguousDefaults).to_dict()
    for definition in document["defs"]["enums"].values():
        assert set(definition) == {"name", "members"}


def test_an_enum_whose_values_are_not_portable_still_serializes():
    """contract.md: "A member's value may be a tuple or an object"."""
    holder = make_dataclass("H", [("w", _Unportable, field(default=_Unportable.PAIR))])
    document = struct_of(holder).to_dict()

    assert document["defs"]["enums"]["_Unportable"]["members"] == ["PAIR", "THING", "BAG"]
    assert json.loads(json.dumps(document)) == document


def test_an_enum_definition_is_shared_while_extras_stay_on_each_occurrence():
    """contract.md: extras belong to a node, never to the definition it points at."""
    holder = make_dataclass("H", [
        ("one", Annotated[_Role, Extra("app.ui", "left")], field(default=_Role.ADMIN)),
        ("two", Annotated[_Role, Extra("app.ui", "right")], field(default=_Role.USER)),
        ("three", _Role, field(default=_Role.USER)),
    ])
    document = struct_of(holder).to_dict()

    assert list(document["defs"]["enums"]) == ["_Role"]
    assert set(document["defs"]["enums"]["_Role"]) == {"name", "members"}
    assert _field_node(document, "H", "one")["shape"][0] == {
        "type": "enum", "ref": "_Role", "extras": {"app.ui": "left"}}
    assert _field_node(document, "H", "two")["shape"][0] == {
        "type": "enum", "ref": "_Role", "extras": {"app.ui": "right"}}
    assert _field_node(document, "H", "three")["shape"][0] == {
        "type": "enum", "ref": "_Role"}


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls", [_Node, _MutualA, _ManyWays, _PlainDefaults,
                                 _AmbiguousDefaults, _FactoryDefaults, _NamesakeHolder],
                         ids=["node", "mutual", "many_ways", "plain_defaults",
                              "ambiguous_defaults", "factory_defaults", "namesakes"])
def test_two_compilations_serialize_byte_for_byte_without_sort_keys(cls):
    """contract.md, Two guarantees: "`json.dumps` needs no `sort_keys`"."""
    a = struct_of(cls).to_dict()
    b = struct_of(cls).to_dict()
    assert json.dumps(a) == json.dumps(b)


def test_key_order_is_fixed_rather_than_merely_equal():
    document = struct_of(_Node).to_dict()
    assert list(document) == ["v", "kind", "root", "defs"]
    assert list(_definition(document, "_Node")) == ["name", "fields"]
    assert list(_field_node(document, "_Node", "parent")) == ["name", "default", "shape"]


def test_a_signature_document_keeps_its_own_fixed_key_order():
    def upload(path: str, count: int = 1):
        """Upload a document."""

    assert list(signature_of(upload).to_dict()) == ["v", "kind", "name", "doc",
                                                    "params", "defs"]


_HASH_SEED_PROGRAM = """
import json
from dataclasses import dataclass, field, make_dataclass
from datetime import date
from enum import Enum
from typing import Annotated

from pytypehint import Extra, struct_of


class Role(Enum):
    ADMIN = "a"
    USER = "u"
    ROOT = ADMIN


class Status(Enum):
    OPEN = 1
    CLOSED = 2


def point():
    @dataclass
    class P:
        v: int = 0
        w: str = "x"
    return P


One, Two, Three = point(), point(), point()


@dataclass
class Inner:
    n: int = 1
    when: date = date(2024, 1, 1)


@dataclass
class Wide:
    a: One = field(default_factory=One)
    b: Two = field(default_factory=Two)
    c: Three = field(default_factory=Three)
    role: Annotated[Role, Extra("z.k", "1"), Extra("a.k", "2")] = Role.USER
    status: Status = Status.CLOSED
    inner: Inner = field(default_factory=Inner)
    ambiguous: str | date = date(2024, 6, 1)
    members: list[Role] = field(default_factory=lambda: [Role.ADMIN, Role.USER])


print(json.dumps({"document": struct_of(Wide).to_dict(),
                  "probe": hash("pytypehint")}))
"""

_HASH_SEEDS = ["0", "1", "7", "424242"]


def _run_with_hash_seed(seed: str) -> dict:
    env = dict(os.environ, PYTHONHASHSEED=seed)
    finished = subprocess.run([sys.executable, "-c", _HASH_SEED_PROGRAM],
                              capture_output=True, text=True, env=env, check=True)
    return json.loads(finished.stdout)


def test_the_document_is_identical_across_hash_seeds():
    """contract.md, Two guarantees: "byte for byte, across processes and hash seeds"."""
    runs = [_run_with_hash_seed(seed) for seed in _HASH_SEEDS]

    # The seeds really did take effect, so the equality below is not vacuous.
    assert len({run["probe"] for run in runs}) > 1

    documents = [json.dumps(run["document"]) for run in runs]
    assert len(set(documents)) == 1


def test_a_subprocess_document_matches_the_one_built_in_this_process():
    """Determinism across processes, not only within one."""
    first = _run_with_hash_seed(_HASH_SEEDS[0])["document"]
    second = _run_with_hash_seed(_HASH_SEEDS[-1])["document"]
    assert json.dumps(first) == json.dumps(second)


# ---------------------------------------------------------------------------
# Defaults: the portable spelling
# ---------------------------------------------------------------------------

_PLAIN_SPELLINGS = [
    pytest.param("an_int", 7, id="int"),
    pytest.param("a_float", 1.5, id="float"),
    pytest.param("a_whole_float", 2.0, id="whole_float"),
    pytest.param("a_str", "hi", id="str"),
    pytest.param("a_true", True, id="bool_true"),
    pytest.param("a_false", False, id="bool_false"),
    pytest.param("a_none", None, id="none"),
    pytest.param("a_date", "2024-06-01", id="date"),
    pytest.param("a_time", "09:30:15", id="time"),
    pytest.param("an_enum_member", "USER", id="enum_member"),
    pytest.param("a_list_of_scalars", ["a", "b"], id="list_of_scalars"),
    pytest.param("a_list_of_dates", ["2020-01-01", "2021-02-03"], id="list_of_dates"),
    pytest.param("a_nested_list", [[1, 2], [3]], id="nested_list"),
    pytest.param("a_list_of_enum_members", ["ADMIN", "USER"], id="list_of_enum_members"),
    pytest.param("an_empty_list", [], id="empty_list"),
    pytest.param("a_nested_dataclass", {"n": 1, "when": "2024-01-01"},
                 id="nested_dataclass"),
    pytest.param("a_shipped_in_a_union", {"$type": "_Shipped", "on": "2024-01-01"},
                 id="dataclass_in_a_union"),
    pytest.param("a_cancelled_in_a_union", {"$type": "_Cancelled", "reason": "none given"},
                 id="other_dataclass_in_a_union"),
]

_AMBIGUOUS_SPELLINGS = [
    pytest.param("str_or_date_with_a_date", {"$type": "date", "$value": "2024-06-01"},
                 id="str_or_date__date"),
    pytest.param("str_or_date_with_a_str", {"$type": "str", "$value": "2024-06-01"},
                 id="str_or_date__str"),
    pytest.param("int_or_float_with_an_int", {"$type": "int", "$value": 10},
                 id="int_or_float__int"),
    pytest.param("int_or_float_with_a_float", {"$type": "float", "$value": 1.5},
                 id="int_or_float__float"),
    pytest.param("int_or_float_with_a_whole_float", {"$type": "float", "$value": 2.0},
                 id="int_or_float__whole_float"),
    pytest.param("date_or_time_with_a_date", {"$type": "date", "$value": "2024-06-01"},
                 id="date_or_time__date"),
    pytest.param("date_or_time_with_a_time", {"$type": "time", "$value": "09:30:00"},
                 id="date_or_time__time"),
    pytest.param("enum_or_str_with_a_member", {"$type": "_Role", "$value": "ADMIN"},
                 id="enum_or_str__member"),
    pytest.param("enum_or_str_with_a_str", {"$type": "str", "$value": "ADMIN"},
                 id="enum_or_str__str"),
    pytest.param("enum_or_enum_with_a_role", {"$type": "_Role", "$value": "USER"},
                 id="enum_or_enum__first"),
    pytest.param("enum_or_enum_with_a_status", {"$type": "_Status", "$value": "OPEN"},
                 id="enum_or_enum__second"),
    pytest.param("list_or_list_with_strs", {"$type": "list[str]", "$value": ["a"]},
                 id="list_or_list__strs"),
    pytest.param("list_or_list_with_ints", {"$type": "list[int]", "$value": [1]},
                 id="list_or_list__ints"),
]

_FACTORY_SPELLINGS = [
    pytest.param("an_int", 7, id="factory_int"),
    pytest.param("a_date", "2024-06-01", id="factory_date"),
    pytest.param("a_time", "09:30:15", id="factory_time"),
    pytest.param("an_enum_member", "USER", id="factory_enum_member"),
    pytest.param("a_list_of_scalars", ["a", "b"], id="factory_list_of_scalars"),
    pytest.param("a_list_of_dates", ["2020-01-01"], id="factory_list_of_dates"),
    pytest.param("a_nested_list", [[1, 2], [3]], id="factory_nested_list"),
    pytest.param("a_nested_dataclass", {"n": 1, "when": "2024-01-01"},
                 id="factory_nested_dataclass"),
    pytest.param("a_dataclass_in_a_union", {"$type": "_Cancelled", "reason": "none given"},
                 id="factory_dataclass_in_a_union"),
    pytest.param("an_ambiguous_date", {"$type": "date", "$value": "2024-06-01"},
                 id="factory_ambiguous_date"),
    pytest.param("an_ambiguous_int", {"$type": "int", "$value": 10},
                 id="factory_ambiguous_int"),
]


@pytest.mark.parametrize("name,written", _PLAIN_SPELLINGS)
def test_an_unambiguous_default_is_written_bare(name, written):
    """contract.md, Defaults: "a date as "YYYY-MM-DD", … an enum member as its name"."""
    assert _document_default(_PlainDefaults, name) == written


@pytest.mark.parametrize("name,written", _AMBIGUOUS_SPELLINGS)
def test_an_ambiguous_default_carries_the_wrapper_decode_consumes(name, written):
    """contract.md: "the default carries the same wrapper `decode` consumes"."""
    assert _document_default(_AmbiguousDefaults, name) == written


@pytest.mark.parametrize("name,written", _FACTORY_SPELLINGS)
def test_a_default_factory_writes_its_product_the_same_way(name, written):
    """contract.md: "A `default_factory` is not a special case"."""
    assert _document_default(_FactoryDefaults, name) == written


def test_an_unambiguous_document_carries_no_value_wrapper_anywhere():
    """contract.md, Reading the wire: the wrapper is for a slot where two options
    share a portable spelling, and `_PlainDefaults` has none."""
    assert "$value" not in json.dumps(struct_of(_PlainDefaults).to_dict())


def test_a_dataclass_in_a_union_uses_the_inline_type_not_the_wrapper():
    """contract.md, Defaults: "A dataclass default in a union of two or more
    dataclasses uses the inline `$type` the core already uses, not the wrapper"."""
    written = _document_default(_PlainDefaults, "a_shipped_in_a_union")
    assert set(written) == {"$type", "on"}
    assert "$value" not in written


def test_a_dataclass_in_a_slot_of_its_own_carries_no_discriminator():
    written = _document_default(_PlainDefaults, "a_nested_dataclass")
    assert "$type" not in written


@pytest.mark.parametrize("name,written", _AMBIGUOUS_SPELLINGS)
def test_a_wrapped_default_has_exactly_the_two_reserved_keys(name, written):
    value = _document_default(_AmbiguousDefaults, name)
    assert set(value) == {"$type", "$value"}


@pytest.mark.parametrize("cls,names", [
    pytest.param(_PlainDefaults, [p.values[0] for p in _PLAIN_SPELLINGS], id="plain"),
    pytest.param(_AmbiguousDefaults, [p.values[0] for p in _AMBIGUOUS_SPELLINGS],
                 id="ambiguous"),
    pytest.param(_FactoryDefaults, [p.values[0] for p in _FACTORY_SPELLINGS],
                 id="factory"),
])
def test_every_written_default_is_json(cls, names):
    """A portable tree and nothing else, so a default survives a real transport."""
    document = struct_of(cls).to_dict()
    for name in names:
        written = _field_node(document, cls.__name__, name)["default"]
        assert json.loads(json.dumps(written)) == written


# ---------------------------------------------------------------------------
# Defaults: the round trip through decode
# ---------------------------------------------------------------------------

_ROUND_TRIPS = (
    [pytest.param(_PlainDefaults, p.values[0], id=f"plain__{p.id}")
     for p in _PLAIN_SPELLINGS]
    + [pytest.param(_AmbiguousDefaults, p.values[0], id=f"ambiguous__{p.id}")
       for p in _AMBIGUOUS_SPELLINGS]
    + [pytest.param(_FactoryDefaults, p.values[0], id=f"factory__{p.id}")
       for p in _FACTORY_SPELLINGS]
)


@pytest.mark.parametrize("cls,name", _ROUND_TRIPS)
def test_a_written_default_reads_back_as_the_field_default(cls, name):
    """contract.md, It speaks decode's language:

        schema.decode({"birthday": field["default"]})   # the field's default, exactly

    Read through the whole pipeline decode.md fixes — `build(decode(x))` — because
    a dataclass default arrives as a dict and `build` is what constructs it.
    """
    assert _round_trip(cls, name) == _compiled_default(cls, name)


@pytest.mark.parametrize("cls,name", _ROUND_TRIPS)
def test_a_written_default_reads_back_with_the_same_type(cls, name):
    """Equality alone would let `1` stand for `1.0` and `True` for `1`."""
    assert type(_round_trip(cls, name)) is type(_compiled_default(cls, name))


@pytest.mark.parametrize("cls,name", _ROUND_TRIPS)
def test_a_written_default_survives_a_real_json_transport(cls, name):
    """The document is the wire, so the round trip must hold through JSON text."""
    schema = struct_of(cls)
    written = _field_node(schema.to_dict(), cls.__name__, name)["default"]
    revived = json.loads(json.dumps({name: written}))
    assert getattr(schema.build(schema.decode(revived)), name) == _compiled_default(cls, name)


# ---------------------------------------------------------------------------
# Defaults: the wrapper one level down
#
# SUSPECTED BUG (all six tests in this block).
#
# contract.md states the wrapper rule per *slot*, not per field:
#
#   "Reading the wire from the document" — "any other option in a slot where two
#   or more options share a portable spelling — send {"$type": <id>, "$value":
#   <portable>}".
#   "Shape nodes" — of a list's `item`: "it is the set of options *one element*
#   may take".
#
# `contract.py::_default` applies the wrapper, but it is only ever called for the
# outermost value of a field. `_written` descends into a list with
# `_portable(shape.item, item)` and into a nested dataclass with
# `_portable(f.shape, ...)`, and `_portable` never wraps. So an element of
# `list[str | date]`, or a field of a nested dataclass default, is written bare
# in a slot where the bare spelling names nothing.
#
# The consequence is silent, which is what makes it worth failing over: the
# document says `["2024-06-01"]`, decode leaves it a `str` because the item slot
# is ambiguous, and `build` then files a `date` default under the `str` option
# beside it without raising. contract.md promises the opposite — "a default taken
# from this document is valid input to `decode`, with no translation in between".
# ---------------------------------------------------------------------------

_NESTED_WRAPPER_CASES = [
    pytest.param("list_of_str_or_date", [{"$type": "date", "$value": "2024-06-01"}],
                 id="list_of_str_or_date"),
    pytest.param("list_of_enum_or_str", [{"$type": "_Role", "$value": "ADMIN"}],
                 id="list_of_enum_or_str"),
    pytest.param("list_of_date_or_time", [{"$type": "time", "$value": "09:30:00"}],
                 id="list_of_date_or_time"),
    pytest.param("list_of_enum_or_enum", [{"$type": "_Status", "$value": "OPEN"}],
                 id="list_of_enum_or_enum"),
    pytest.param("list_of_int_or_float", [{"$type": "float", "$value": 2.0}],
                 id="list_of_int_or_float"),
    pytest.param("grid_of_str_or_date", [[{"$type": "date", "$value": "2020-01-01"}]],
                 id="grid_of_str_or_date"),
    pytest.param("nested_dataclass", {"when": {"$type": "date", "$value": "2024-06-01"},
                                      "role": {"$type": "_Role", "$value": "ADMIN"}},
                 id="nested_dataclass"),
]


@pytest.mark.parametrize("name,written", _NESTED_WRAPPER_CASES)
def test_an_ambiguous_slot_inside_a_default_carries_the_wrapper_too(name, written):
    # SUSPECTED BUG: see the block comment above. `_written` reaches nested values
    # through `_portable`, which never applies the wrapper, so only the outermost
    # slot of a default is ever named.
    assert _document_default(_NestedAmbiguousDefaults, name) == written


@pytest.mark.parametrize("name", [
    "list_of_str_or_date", "list_of_enum_or_str", "list_of_date_or_time",
    "list_of_enum_or_enum", "grid_of_str_or_date", "nested_dataclass",
], ids=["list_of_str_or_date", "list_of_enum_or_str", "list_of_date_or_time",
        "list_of_enum_or_enum", "grid_of_str_or_date", "nested_dataclass"])
def test_a_default_with_an_ambiguous_slot_inside_it_reads_back_unchanged(name):
    # SUSPECTED BUG: the round trip silently returns a `str` where a `date` or an
    # enum member was, and `build` accepts it because `str` is a real option of
    # the slot. Nothing raises; the default simply changes meaning on the wire.
    assert _round_trip(_NestedAmbiguousDefaults, name) == _compiled_default(
        _NestedAmbiguousDefaults, name)


@pytest.mark.parametrize("name", ["list_of_str_or_date", "list_of_enum_or_str",
                                  "list_of_date_or_time", "list_of_enum_or_enum"],
                         ids=["list_of_str_or_date", "list_of_enum_or_str",
                              "list_of_date_or_time", "list_of_enum_or_enum"])
def test_a_default_with_an_ambiguous_slot_inside_it_keeps_its_python_types(name):
    # SUSPECTED BUG: the type is what is lost, and equality alone would not show it.
    got = _round_trip(_NestedAmbiguousDefaults, name)
    expected = _compiled_default(_NestedAmbiguousDefaults, name)
    assert [type(v) for v in got] == [type(v) for v in expected]


def test_a_nested_dataclass_default_is_not_quietly_refiled_under_another_option():
    # SUSPECTED BUG: the sharpest statement of the defect. `_InnerAmbiguous.when`
    # is a `date` default in a `str | date` slot; the document writes it bare, and
    # the value comes back a `str` with no error anywhere along the way.
    built = _round_trip(_NestedAmbiguousDefaults, "nested_dataclass")
    assert type(built.when) is date
    assert built.role is _Role.ADMIN


@pytest.mark.parametrize("name", ["list_of_str_or_date", "nested_dataclass"],
                         ids=["list", "nested_dataclass"])
def test_every_ambiguous_slot_reached_by_a_default_names_its_option(name):
    # SUSPECTED BUG: stated as the rule rather than as a spelling — wherever the
    # document publishes a value for a slot with two or more portable options, the
    # value must name one of them.
    written = _document_default(_NestedAmbiguousDefaults, name)
    values = written if type(written) is list else list(written.values())
    for value in values:
        assert type(value) is dict and set(value) == {"$type", "$value"}


@pytest.mark.parametrize("name", ["a_date", "a_time", "an_enum_member",
                                  "a_list_of_dates", "a_list_of_enum_members"],
                         ids=["date", "time", "enum_member", "list_of_dates",
                              "list_of_enum_members"])
def test_decode_alone_restores_a_default_that_needs_no_construction(name):
    """The shorter form contract.md shows: decode is enough where no dataclass is
    involved."""
    schema = struct_of(_PlainDefaults)
    written = _field_node(schema.to_dict(), "_PlainDefaults", name)["default"]
    assert schema.decode({name: written})[name] == _compiled_default(_PlainDefaults, name)


def test_a_decoded_enum_default_is_the_member_itself():
    """decode.md: "Decode returns the member itself, not a copy"."""
    schema = struct_of(_PlainDefaults)
    written = _field_node(schema.to_dict(), "_PlainDefaults", "an_enum_member")["default"]
    assert schema.decode({"an_enum_member": written})["an_enum_member"] is _Role.USER


# ---------------------------------------------------------------------------
# Defaults: absence, null, and the recipe
# ---------------------------------------------------------------------------

def test_a_field_without_a_default_omits_the_key():
    """contract.md: "A field with no default omits the key entirely, which is how
    `MISSING` is expressed"."""
    document = struct_of(_PartlyDefaulted).to_dict()
    assert "default" not in _field_node(document, "_PartlyDefaulted", "without_default")
    assert _field_node(document, "_PartlyDefaulted", "with_default")["default"] == 3


def test_an_absent_default_is_never_spelled_as_null():
    document = struct_of(_PartlyDefaulted).to_dict()
    node = _field_node(document, "_PartlyDefaulted", "without_default")
    assert list(node) == ["name", "shape"]


def test_a_none_default_is_written_as_null():
    """contract.md: "`null` … says the default is None"."""
    document = struct_of(_Node).to_dict()
    assert _field_node(document, "_Node", "parent")["default"] is None


def test_absent_and_null_defaults_are_two_different_states():
    document = struct_of(
        make_dataclass("H", [("absent", int),
                             ("null", int | None, field(default=None))])).to_dict()
    assert "default" not in _field_node(document, "H", "absent")
    assert _field_node(document, "H", "null")["default"] is None


def test_a_default_factory_emits_the_product_not_a_factory_marker():
    """contract.md: "`Field.default` is the certified *product*"."""
    holder = make_dataclass("H", [
        ("xs", list[str], field(default_factory=lambda: ["a", "b"])),
        ("inner", _Inner, field(default_factory=_Inner)),
    ])
    document = struct_of(holder).to_dict()

    assert _field_node(document, "H", "xs")["default"] == ["a", "b"]
    assert _field_node(document, "H", "inner")["default"] == {"n": 1, "when": "2024-01-01"}
    text = json.dumps(document)
    assert "Factory" not in text
    assert "lambda" not in text


def test_an_impure_factory_is_sampled_once_and_the_document_never_moves():
    """contract.md: "An impure recipe makes the written default a sample of one
    serving" — one serving, taken at compile time and never retaken."""
    servings = []

    def recipe():
        servings.append(len(servings) + 1)
        return list(servings)

    schema = struct_of(make_dataclass(
        "H", [("xs", list[int], field(default_factory=recipe))]))
    after_compilation = len(servings)

    documents = [schema.to_dict() for _ in range(3)]
    assert len(servings) == after_compilation
    assert documents[0] == documents[1] == documents[2]
    assert _field_node(documents[0], "H", "xs")["default"] == [1]


def test_running_the_recipe_again_does_not_move_the_document():
    """`resolve` serves a fresh product per missing key; the document keeps its
    sample."""
    servings = []

    def recipe():
        servings.append(1)
        return [len(servings)]

    schema = struct_of(make_dataclass(
        "H", [("xs", list[int], field(default_factory=recipe))]))
    before = schema.to_dict()
    for _ in range(5):
        schema.resolve({})
    assert schema.to_dict() == before


# ---------------------------------------------------------------------------
# A fresh tree on every call
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls", [_Node, _MutualA, _ManyWays, _PlainDefaults,
                                 _AmbiguousDefaults, _FactoryDefaults],
                         ids=["node", "mutual", "many_ways", "plain_defaults",
                              "ambiguous_defaults", "factory_defaults"])
def test_two_calls_on_one_schema_share_no_container(cls):
    """contract.md, Two guarantees: "Nothing in the result is an object the schema
    holds, at any depth"."""
    schema = struct_of(cls)
    first, second = schema.to_dict(), schema.to_dict()
    assert first == second
    assert _container_ids(first) & _container_ids(second) == set()


def test_two_calls_on_two_compilations_share_no_container():
    a, b = struct_of(_PlainDefaults).to_dict(), struct_of(_PlainDefaults).to_dict()
    assert _container_ids(a) & _container_ids(b) == set()


def test_a_signature_document_is_fresh_too():
    def upload(target: _Leaf, count: int = 1):
        pass

    schema = signature_of(upload)
    first, second = schema.to_dict(), schema.to_dict()
    assert first == second
    assert _container_ids(first) & _container_ids(second) == set()


def test_clearing_the_definition_table_is_harmless():
    """contract.md shows exactly this call."""
    schema = struct_of(_ManyWays)
    original = schema.to_dict()

    document = schema.to_dict()
    document["defs"]["structs"].clear()
    document["defs"]["enums"]["injected"] = {"name": "x", "members": []}

    assert schema.to_dict() == original


@pytest.mark.parametrize("mutate,description", [
    pytest.param(lambda d: d["defs"]["structs"].pop("_Leaf"), "drop a definition",
                 id="definition"),
    pytest.param(lambda d: _definition(d, "_ManyWays")["fields"].clear(), "drop fields",
                 id="field_list"),
    pytest.param(lambda d: _field_node(d, "_ManyWays", "direct").update(default=None),
                 "overwrite a default", id="field_default"),
    pytest.param(lambda d: _field_node(d, "_ManyWays", "direct")["shape"].append(
        {"type": "str"}), "grow a shape slot", id="shape_slot"),
    pytest.param(lambda d: _field_node(d, "_ManyWays", "many")["shape"][0]["item"].clear(),
                 "empty a list item slot", id="list_item"),
    pytest.param(lambda d: _field_node(d, "_ManyWays", "direct")["shape"][0].update(
        ref="nowhere"), "repoint a ref", id="ref"),
])
def test_mutating_the_document_never_reaches_a_later_call(mutate, description):
    schema = struct_of(_ManyWays)
    original = schema.to_dict()

    document = schema.to_dict()
    mutate(document)
    assert document != original

    assert schema.to_dict() == original


def test_mutating_a_nested_default_never_reaches_a_later_call():
    schema = struct_of(_PlainDefaults)
    original = schema.to_dict()

    document = schema.to_dict()
    _field_node(document, "_PlainDefaults", "a_nested_dataclass")["default"]["n"] = 999
    _field_node(document, "_PlainDefaults", "a_nested_list")["default"][0].append(99)
    _field_node(document, "_PlainDefaults", "a_list_of_scalars")["default"].clear()

    assert schema.to_dict() == original


def test_mutating_a_default_never_reaches_the_compiled_schema():
    """The document is written from the certified default, never wired back into it."""
    schema = struct_of(_FactoryDefaults)
    document = schema.to_dict()
    _field_node(document, "_FactoryDefaults", "a_list_of_scalars")["default"].append("z")

    assert _compiled_default(_FactoryDefaults, "a_list_of_scalars") == ["a", "b"]
    assert schema.build({}).a_list_of_scalars == ["a", "b"]


def test_an_extras_dict_is_not_the_one_the_shape_holds():
    holder = make_dataclass("H", [
        ("one", Annotated[_Role, Extra("app.ui", "left")], field(default=_Role.ADMIN))])
    schema = struct_of(holder)
    document = schema.to_dict()
    _field_node(document, "H", "one")["shape"][0]["extras"]["app.ui"] = "tampered"

    assert _field_node(schema.to_dict(), "H", "one")["shape"][0]["extras"] == {
        "app.ui": "left"}


@pytest.mark.parametrize("cls", [_Node, _ManyWays, _PlainDefaults],
                         ids=["node", "many_ways", "plain_defaults"])
def test_a_document_shares_no_container_with_itself(cls):
    """No definition is aliased into two places, so a reader may edit any subtree."""
    document = struct_of(cls).to_dict()
    seen = set()
    total = 0

    def visit(tree):
        nonlocal total
        if type(tree) in (dict, list):
            total += 1
            seen.add(id(tree))
            values = tree.values() if type(tree) is dict else tree
            for value in values:
                visit(value)

    visit(document)
    assert len(seen) == total


def test_the_number_of_definitions_matches_the_number_of_compiled_structs():
    """A sanity tie between the graph the core holds and the tables it writes."""
    schema = struct_of(_ManyWays)
    reached = set()

    def visit(struct):
        if id(struct) in reached:
            return
        reached.add(id(struct))
        for f in struct.fields:
            for option in f.shape:
                for inner in (option.item if type(option) is List else (option,)):
                    if type(inner) is Struct:
                        visit(inner)

    visit(schema)
    assert len(struct_of(_ManyWays).to_dict()["defs"]["structs"]) == len(reached)


def test_dataclass_fields_of_the_default_carriers_are_all_covered():
    """The spelling tables above must not silently fall behind their dataclasses."""
    for cls, params in ((_PlainDefaults, _PLAIN_SPELLINGS),
                        (_AmbiguousDefaults, _AMBIGUOUS_SPELLINGS),
                        (_FactoryDefaults, _FACTORY_SPELLINGS)):
        covered = {p.values[0] for p in params}
        assert {f.name for f in dc_fields(cls)} == covered

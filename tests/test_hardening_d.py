"""Union torture (release hardening, agent D).

The property under attack, in one sentence:

    a branch of a union can never be selected incorrectly without an error.

Concretely: if a slot's options are told apart by an identity, then a payload
sent under identity X either becomes a value of branch X, or is refused. It may
never be "dropped" so that a neighbouring branch — the `str` beside a `date`, the
`int` beside a `float` — accepts it in silence.

Everything here is derived from the *published document* rather than from the
compiled shapes, so a divergence between what `to_dict` writes, what `decode`
reads and what `build`/`resolve` accept shows up as a failure rather than as
matching internals.
"""

import copy
import json
import random
from dataclasses import dataclass, field, fields as dc_fields, is_dataclass, make_dataclass
from datetime import date, time
from enum import Enum
from typing import Annotated, Literal, Optional, Union

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from pytypehint import (
    Choices, EnumShape, Field, List, Min, SchemaTypeError, SchemaValueError, Str,
    signature_of, struct_of,
)
from pytypehint.shapes import List as ListShape
from pytypehint.structure import Struct as StructShape, _portable_options

TYPE = "$type"
VALUE = "$value"

D = date(2026, 8, 8)
T = time(14, 30)


# ---------------------------------------------------------------------------
# Fixtures for the matrix
# ---------------------------------------------------------------------------

class Role(Enum):
    ADMIN = "a"
    USER = "u"
    SUPER = "a"          # alias of ADMIN


class Status(Enum):
    ADMIN = "z"          # same member name as Role.ADMIN, on purpose
    CLOSED = "y"


class Cross(Enum):
    RED = "BLUE"         # name and value cross over
    BLUE = "RED"


class Tag(str, Enum):    # an enum whose members are also str instances
    ONE = "one"


class Level(int, Enum):  # an enum whose members are also int instances
    LOW = 1


@dataclass
class SA:
    a: int


@dataclass
class SB:
    b: str


@dataclass
class W1:
    v: str | date


@dataclass
class W2:
    v: int | float


@dataclass
class W3:
    v: list[str] | list[int]


@dataclass
class W4:
    v: Role | Status


@dataclass
class Node:
    kid: "Node | str | date | None" = None


REGISTRY = {
    ("enum", "Role"): Role, ("enum", "Status"): Status, ("enum", "Cross"): Cross,
    ("enum", "Tag"): Tag, ("enum", "Level"): Level,
    ("struct", "SA"): SA, ("struct", "SB"): SB, ("struct", "W1"): W1,
    ("struct", "W2"): W2, ("struct", "W3"): W3, ("struct", "W4"): W4,
}


def schema_of(annotation, default=...):
    namespace: dict = {"__annotations__": {"f": annotation}}
    if default is not ...:
        namespace["f"] = default
    return struct_of(dataclass(type("Holder", (), namespace)))


def field_slot(schema):
    document = schema.to_dict()
    root = document["defs"]["structs"][document["root"]]
    return document, root["fields"][0]["shape"]


# ---------------------------------------------------------------------------
# A sender that knows only the document
#
# docs/contract.md, "Reading the wire from the document": a struct option in a
# slot with two or more struct options carries an inline "$type"; any other
# option in a slot where two or more options share a portable spelling travels
# in a "$type"/"$value" wrapper; everything else goes bare.
# ---------------------------------------------------------------------------

SPELLING = {"int": "number", "float": "number",
            "str": "text", "date": "text", "time": "text", "enum": "text",
            "bool": "boolean", "none": "null", "list": "array", "struct": "object"}


def slot_modes(nodes):
    spellings = [SPELLING[n["type"]] for n in nodes]
    structs = sum(1 for n in nodes if n["type"] == "struct")
    modes = []
    for node, spelling in zip(nodes, spellings):
        if node["type"] == "struct":
            modes.append("inline" if structs > 1 else "bare")
        elif spellings.count(spelling) > 1:
            modes.append("wrapper")
        else:
            modes.append("bare")
    return modes


def node_pytype(node, document):
    simple = {"int": int, "float": float, "str": str, "bool": bool,
              "date": date, "time": time, "none": type(None), "list": list}
    kind = node["type"]
    if kind in simple:
        return simple[kind]
    table = "enums" if kind == "enum" else "structs"
    return REGISTRY[(kind, document["defs"][table][node["ref"]]["name"])]


def _limits_ok(node, value):
    kind = node["type"]
    if kind == "str":
        if "min_length" in node and len(value) < node["min_length"]:
            return False
        if "max_length" in node and len(value) > node["max_length"]:
            return False
        return "choices" not in node or value in node["choices"]
    if kind in ("int", "float", "date", "time"):
        written = value if kind in ("int", "float") else (
            value.isoformat(timespec="seconds") if kind == "time" else value.isoformat())
        if "min" in node and (written < node["min"]
                              or (node.get("exclusive_min") and written == node["min"])):
            return False
        if "max" in node and (written > node["max"]
                              or (node.get("exclusive_max") and written == node["max"])):
            return False
        if "choices" in node and written not in node["choices"]:
            return False
        return "multiple_of" not in node or value % node["multiple_of"] == 0
    if kind == "list":
        if "min_items" in node and len(value) < node["min_items"]:
            return False
        if "max_items" in node and len(value) > node["max_items"]:
            return False
    return True


def node_accepts(node, value, document):
    if type(value) is not node_pytype(node, document):
        return False
    if not _limits_ok(node, value):
        return False
    if node["type"] == "list":
        return all(slot_accepts(node["item"], item, document) for item in value)
    if node["type"] == "struct":
        definition = document["defs"]["structs"][node["ref"]]
        return all(slot_accepts(f["shape"], getattr(value, f["name"]), document)
                   for f in definition["fields"])
    return True


def slot_accepts(nodes, value, document):
    return any(node_accepts(node, value, document) for node in nodes)


def slot_branches(nodes, value, document):
    """Mirrors validation.value_branch, read off the document alone."""
    by_type = [i for i, n in enumerate(nodes)
               if type(value) is node_pytype(n, document)]
    if len(by_type) < 2:
        return by_type
    return [i for i in by_type if node_accepts(nodes[i], value, document)]


def write_node(node, value, document):
    kind = node["type"]
    if kind == "date":
        return value.isoformat()
    if kind == "time":
        return value.isoformat(timespec="seconds")
    if kind == "enum":
        return value.name
    if kind == "float":
        return float(value)
    if kind == "list":
        return [send(node["item"], item, document) for item in value]
    if kind == "struct":
        definition = document["defs"]["structs"][node["ref"]]
        return {f["name"]: send(f["shape"], getattr(value, f["name"]), document)
                for f in definition["fields"]}
    return value


def send(nodes, value, document, *, branch=None):
    modes = slot_modes(nodes)
    if branch is None:
        candidates = slot_branches(nodes, value, document)
        assert candidates, f"no branch for {value!r}"
        branch = candidates[0]
    node = nodes[branch]
    written = write_node(node, value, document)
    if node["type"] == "struct":
        if modes[branch] == "inline":
            name = document["defs"]["structs"][node["ref"]]["name"]
            return {TYPE: name, **written}
        return written
    if modes[branch] == "wrapper":
        return {TYPE: node["id"], VALUE: written}
    return written


def exactly_equal(left, right):
    """Equality that also pins the exact type, at every depth."""
    if type(left) is not type(right):
        return False
    if type(left) is list:
        return len(left) == len(right) and all(
            exactly_equal(a, b) for a, b in zip(left, right))
    if type(left) is dict:
        return set(left) == set(right) and all(
            exactly_equal(left[k], right[k]) for k in left)
    if is_dataclass(type(left)):
        return all(exactly_equal(getattr(left, f.name), getattr(right, f.name))
                   for f in dc_fields(left))
    return left == right


def outcome(schema, wire):
    """decode then build. decode is never allowed to raise a schema error."""
    prepared = schema.decode({"f": copy.deepcopy(wire)})
    try:
        return ("ok", schema.build(prepared).f, prepared["f"])
    except (SchemaTypeError, SchemaValueError, TypeError, ValueError) as error:
        return ("refused", f"{type(error).__name__}: {error}", prepared["f"])


# ---------------------------------------------------------------------------
# The combination matrix
# ---------------------------------------------------------------------------

MATRIX: list[tuple[str, object, list]] = [
    ("str|date", str | date, ["hi", "2026-08-08", D]),
    ("str|time", str | time, ["hi", "14:30", T]),
    ("date|time", date | time, [D, T]),
    ("int|float", int | float, [3, 0, -1, 3.0, 3.5, 0.0]),
    ("bool|int", bool | int, [True, False, 1, 0]),
    ("bool|float", bool | float, [True, 1.0]),
    ("int|float|bool", int | float | bool, [3, 3.0, True]),
    ("Role|Status", Role | Status, [Role.ADMIN, Status.ADMIN]),
    ("str|Role", str | Role, ["ADMIN", "a", Role.ADMIN, Role.USER]),
    ("date|Role", date | Role, [D, Role.USER]),
    ("str|Cross", str | Cross, ["RED", Cross.RED, Cross.BLUE]),
    ("str|Tag", str | Tag, ["ONE", Tag.ONE]),
    ("int|Level", int | Level, [1, Level.LOW]),
    ("list[str]|list[int]", list[str] | list[int], [["a"], [1], [], ["a", "b"]]),
    ("list[str]|list[date]", list[str] | list[date], [["a"], [D], []]),
    ("list[int]|list[float]", list[int] | list[float], [[1], [1.0], []]),
    ("list[str|date]", list[str | date], [["a", D], [], [D]]),
    ("list[list[str|date]]", list[list[str | date]], [[["a", D]], [[]], []]),
    ("list[list[str]]|list[list[int]]", list[list[str]] | list[list[int]],
     [[["a"]], [[1]], []]),
    ("SA|SB", SA | SB, [SA(1), SB("x")]),
    ("list[SA|SB]", list[SA | SB], [[SA(1), SB("x")], []]),
    ("list[SA]|list[SB]", list[SA] | list[SB], [[SA(1)], [SB("q")]]),
    ("SA|str|date", SA | str | date, [SA(1), "hi", D]),
    ("SA|SB|str|date", SA | SB | str | date, [SA(1), SB("y"), "hi", D]),
    ("SA|list[str]|list[int]", SA | list[str] | list[int], [SA(1), ["a"], [2]]),
    ("SA|SB|list[str]|list[int]", SA | SB | list[str] | list[int],
     [SA(1), SB("x"), ["a"], [2]]),
    ("W1|W2", W1 | W2, [W1("hi"), W1(D), W2(3), W2(3.0)]),
    ("W1|W3|W4", W1 | W3 | W4,
     [W1(D), W3(["a"]), W3([1]), W4(Role.ADMIN), W4(Status.ADMIN)]),
    ("list[W1|W4]", list[W1 | W4], [[W1(D), W4(Status.ADMIN)]]),
    ("Opt[str|date]", Optional[str | date], ["hi", D, None]),
    ("Opt[int|float]", Optional[int | float], [3, 3.0, None]),
    ("Opt[date|time]", Optional[date | time], [D, T, None]),
    ("Opt[Role|Status]", Optional[Role | Status], [Role.ADMIN, Status.CLOSED, None]),
    ("Opt[list[str]|list[int]]", Optional[list[str] | list[int]], [["a"], [1], None]),
    ("Opt[SA|SB]", Optional[SA | SB], [SA(1), SB("x"), None]),
    ("Opt[list[str|date]]", Optional[list[str | date]], [["a", D], None]),
    ("str|date|time|int|float", str | date | time | int | float,
     ["hi", D, T, 3, 3.0]),
    ("str|date|Role|int|float|bool|None",
     str | date | Role | int | float | bool | None,
     ["hi", D, Role.USER, 3, 3.0, True, None]),
    ("list[str]|str", list[str] | str, [["a"], "a"]),
    ("list[str]|SA", list[str] | SA, [["a"], SA(2)]),
    ("list[Role|Status]", list[Role | Status], [[Role.ADMIN, Status.ADMIN]]),
    ("list[int|float]", list[int | float], [[1, 1.0, 2.5]]),
    ("Lit|date", Union[Literal["a", "b"], date], ["a", D]),
    ("Lit-int|float", Union[Literal[1, 2], float], [1, 2.5]),
]

MATRIX_IDS = [name for name, _, _ in MATRIX]


@pytest.mark.parametrize("annotation,values", [(a, v) for _, a, v in MATRIX],
                         ids=MATRIX_IDS)
def test_document_rule_matches_the_decoder(annotation, values):
    """What contract.md tells a sender is exactly what decode reads."""
    schema = schema_of(annotation)
    document, nodes = field_slot(schema)
    wants_wrapper = [mode == "wrapper" for mode in slot_modes(nodes)]
    shapes = schema.fields[0].shape
    portable = _portable_options(shapes)
    for index, (node, shape) in enumerate(zip(nodes, shapes)):
        if node["type"] == "struct":
            continue
        reads_wrapper = any(shape is option for option in portable)
        assert wants_wrapper[index] == reads_wrapper, (
            f"option {index} ({node['type']}): document says "
            f"wrapper={wants_wrapper[index]}, decode says {reads_wrapper}")


@pytest.mark.parametrize("annotation,values", [(a, v) for _, a, v in MATRIX],
                         ids=MATRIX_IDS)
def test_every_branch_is_reachable_from_the_document(annotation, values):
    """A sender that reads only the document lands on the branch it named."""
    schema = schema_of(annotation)
    document, nodes = field_slot(schema)
    for value in values:
        wire = json.loads(json.dumps(send(nodes, value, document)))
        state, result, _ = outcome(schema, wire)
        assert state == "ok", f"{value!r} via {wire!r}: {result}"
        assert exactly_equal(result, value), f"{value!r} via {wire!r} -> {result!r}"


@pytest.mark.parametrize("annotation,values", [(a, v) for _, a, v in MATRIX],
                         ids=MATRIX_IDS)
def test_no_branch_smuggles_another_branchs_payload(annotation, values):
    """THE critical property, over every ordered pair of branches of every slot."""
    schema = schema_of(annotation)
    document, nodes = field_slot(schema)
    modes = slot_modes(nodes)
    for named, node in enumerate(nodes):
        if modes[named] != "wrapper":
            continue
        for value in values:
            for other in slot_branches(nodes, value, document):
                if other == named:
                    continue
                payload = write_node(nodes[other], value, document)
                wire = json.loads(json.dumps({TYPE: node["id"], VALUE: payload}))
                state, result, _ = outcome(schema, wire)
                if state == "refused":
                    continue
                assert node_accepts(node, result, document), (
                    f'{{"$type": {node["id"]!r}}} carrying a '
                    f'{nodes[other]["type"]} payload {payload!r} was accepted as '
                    f"{result!r} ({type(result).__name__})")


# The payloads a named branch cannot possibly produce. Consuming any of these
# would file the value under the neighbour that does read its raw spelling.
UNREACHABLE = [
    ("str|date", str | date, "date", "2026-02-31"),
    ("str|date", str | date, "date", "2026-13-01"),
    ("str|date", str | date, "date", "20260808"),
    ("str|date", str | date, "date", "2026-08-08T10:00"),
    ("str|date", str | date, "date", "2026/08/08"),
    ("str|date", str | date, "date", "2026-W32-6"),
    ("str|time", str | time, "time", "25:00"),
    ("str|time", str | time, "time", "10:60"),
    ("str|time", str | time, "time", "1430"),
    ("str|time", str | time, "time", "2020"),
    ("str|Role", str | Role, "Role", "NOPE"),
    ("str|Role", str | Role, "Role", "admin"),
    ("str|Role", str | Role, "Role", "a"),          # the value, not the name
    ("str|Tag", str | Tag, "Tag", "one"),           # the value, not the name
    ("int|float", int | float, "float", 10 ** 400),
    ("int|float", int | float, "float", -(10 ** 400)),
    ("date|time", date | time, "date", "2026-02-31"),
    ("date|time", date | time, "time", "25:00"),
    ("Role|Status", Role | Status, "Role", "NOPE"),
    ("SA|str|date", SA | str | date, "date", "2026-02-31"),
    ("SA|SB|str|date", SA | SB | str | date, "date", "2026-02-31"),
    ("Opt[str|date]", Optional[str | date], "date", "2026-02-31"),
    ("Ann[str,Choices]|date", Union[Annotated[str, Choices(values=("keep",))], date],
     "date", "2026-02-31"),
]


@pytest.mark.parametrize("annotation,named,payload",
                         [(a, n, p) for _, a, n, p in UNREACHABLE],
                         ids=[f"{lbl}:{n}={p!r}" for lbl, _, n, p in UNREACHABLE])
def test_a_payload_that_cannot_reach_its_branch_is_refused(annotation, named, payload):
    schema = schema_of(annotation)
    wire = {TYPE: named, VALUE: payload}
    state, result, prepared = outcome(schema, wire)
    assert prepared == wire, "decode consumed a wrapper whose payload missed its option"
    assert state == "refused", f"{wire!r} was accepted as {result!r}"


ITEM_UNREACHABLE = [
    ("list[str|date]", list[str | date], "date", "2026-02-31"),
    ("list[str|Role]", list[str | Role], "Role", "NOPE"),
    ("list[int|float]", list[int | float], "float", 10 ** 400),
]


@pytest.mark.parametrize("annotation,named,payload",
                         [(a, n, p) for _, a, n, p in ITEM_UNREACHABLE],
                         ids=[lbl for lbl, _, _, _ in ITEM_UNREACHABLE])
def test_the_same_holds_in_a_list_element_slot(annotation, named, payload):
    schema = schema_of(annotation)
    wire = [{TYPE: named, VALUE: payload}]
    state, result, prepared = outcome(schema, wire)
    assert prepared == wire
    assert state == "refused", f"{wire!r} was accepted as {result!r}"


# A real value the named branch refuses must keep reporting as THAT branch.
REFUSED_BY_ITS_OWN_BRANCH = [
    (Union[Annotated[date, Min(date(2030, 1, 1))], str], "date", "2026-08-08", date),
    (Union[time, str], "time", "10:00:00.5", time),
    (Union[time, str], "time", "10:00:00+02:00", time),
    (Union[Annotated[int, Min(100)], float], "int", 5, int),
]


@pytest.mark.parametrize("annotation,named,payload,pytype", REFUSED_BY_ITS_OWN_BRANCH)
def test_a_limit_violation_is_not_demoted_to_the_neighbour(annotation, named,
                                                           payload, pytype):
    schema = schema_of(annotation)
    prepared = schema.decode({"f": {TYPE: named, VALUE: payload}})
    assert type(prepared["f"]) is pytype, "decode failed to reach the named option"
    with pytest.raises((SchemaTypeError, SchemaValueError)):
        schema.build(prepared)


# ---------------------------------------------------------------------------
# Malformed wrappers, and wrappers in the wrong slot
# ---------------------------------------------------------------------------

MALFORMED = [
    {VALUE: "x"},
    {TYPE: 1, VALUE: "x"},
    {TYPE: None, VALUE: "x"},
    {TYPE: {}, VALUE: "x"},
    {TYPE: [], VALUE: "x"},
    {TYPE: ["date"], VALUE: "x"},
    {TYPE: "nope"},
    {TYPE: "nope", VALUE: "x"},
    {TYPE: "None", VALUE: None},
    {},
    {"note": 1},
    {TYPE: "date"},
    {TYPE: "date", VALUE: "2026-08-08", "extra": 1},
    {TYPE: "date", VALUE: {TYPE: "date", VALUE: "2026-08-08"}},
    {TYPE: "date", VALUE: "2026-08-08", 1: "x"},
]


@pytest.mark.parametrize("wire", MALFORMED, ids=range(len(MALFORMED)))
@pytest.mark.parametrize("annotation", [str | date, date | time, str | Role,
                                        int | float, list[str] | list[int],
                                        SA | SB | str | date,
                                        Optional[str | date]],
                         ids=["str|date", "date|time", "str|Role", "int|float",
                              "list[str]|list[int]", "SA|SB|str|date",
                              "Opt[str|date]"])
def test_a_malformed_wrapper_is_handed_back_and_refused(annotation, wire):
    schema = schema_of(annotation)
    original = copy.deepcopy(wire)
    prepared = schema.decode({"f": copy.deepcopy(wire)})
    assert prepared["f"] == original, "decode diagnosed instead of handing it back"
    with pytest.raises((SchemaTypeError, SchemaValueError)):
        schema.build(prepared)


MISPLACED = [
    ("field slot takes an element wrapper", list[str | date],
     {TYPE: "date", VALUE: "2026-08-08"}),
    ("field slot takes its own list identity", list[str | date],
     {TYPE: "list[str | date]", VALUE: ["a"]}),
    ("element slot takes a field wrapper", list[str] | list[date],
     [{TYPE: "date", VALUE: "2026-08-08"}]),
    ("scalar identity at a list-of-lists slot", list[str] | list[date],
     {TYPE: "date", VALUE: "2026-08-08"}),
    ("list identity at a scalar slot", str | date,
     {TYPE: "list[str]", VALUE: ["a"]}),
    ("wrapper on a single-option field", date,
     {TYPE: "date", VALUE: "2026-08-08"}),
    ("wrapper on a single-option element", list[date],
     [{TYPE: "date", VALUE: "2026-08-08"}]),
    ("struct identity inside a wrapper", W1 | W2,
     {TYPE: "W1", VALUE: {"v": "hi"}}),
    ("struct identity inside a wrapper, beside lists",
     SA | SB | list[str] | list[int], {TYPE: "SA", VALUE: {"a": 1}}),
    ("list identity used inline as a struct discriminator",
     SA | SB | list[str] | list[int], {TYPE: "list[str]", "a": 1}),
    ("scalar identity used inline as a struct discriminator",
     SA | SB | str | date, {TYPE: "str", "a": 1}),
    ("no discriminator at all on a struct union", W1 | W2,
     {"v": {TYPE: "date", VALUE: "2026-08-08"}}),
]


@pytest.mark.parametrize("annotation,wire", [(a, w) for _, a, w in MISPLACED],
                         ids=[label for label, _, _ in MISPLACED])
def test_a_wrapper_in_the_wrong_slot_is_refused(annotation, wire):
    schema = schema_of(annotation)
    with pytest.raises((SchemaTypeError, SchemaValueError)):
        schema.build(schema.decode({"f": copy.deepcopy(wire)}))


BARE_AMBIGUOUS = [
    ("date|time", date | time, "2026-08-08"),
    ("date|time", date | time, "14:30"),
    ("Role|Status", Role | Status, "ADMIN"),
    ("list[str]|list[int]", list[str] | list[int], []),
    ("list[str]|list[int]", list[str] | list[int], ["a"]),
    ("list[str]|list[date]", list[str] | list[date], ["2026-08-08"]),
]


@pytest.mark.parametrize("annotation,wire", [(a, w) for _, a, w in BARE_AMBIGUOUS],
                         ids=[label + ":" + repr(w) for label, _, w in BARE_AMBIGUOUS])
def test_a_bare_value_no_option_can_claim_fails_loudly(annotation, wire):
    """Where no option takes the bare spelling, the bare value must not be guessed."""
    schema = schema_of(annotation)
    assert schema.decode({"f": copy.deepcopy(wire)})["f"] == wire
    with pytest.raises((SchemaTypeError, SchemaValueError)):
        schema.build(schema.decode({"f": copy.deepcopy(wire)}))


# ---------------------------------------------------------------------------
# Identity: ambiguity is a compile error, never a silent choice
# ---------------------------------------------------------------------------

def enum_named(name):
    return Enum(name, {"A": "a", "B": "b"})


AMBIGUOUS_SCHEMAS = [
    ("str beside an enum named str", Union[str, enum_named("str")]),
    ("date beside an enum named date", Union[date, enum_named("date")]),
    ("time beside an enum named time", Union[time, enum_named("time")]),
    ("int beside an enum named int", Union[int, enum_named("int")]),
    ("bool beside an enum named bool", Union[bool, enum_named("bool")]),
    ("float beside an enum named float", Union[float, enum_named("float")]),
    ("list[str] beside an enum named list[str]",
     Union[list[str], enum_named("list[str]")]),
    ("None beside an enum named None", Union[None, enum_named("None"), str]),
    ("two dataclasses of one name",
     Union[make_dataclass("Same", [("x", int)]), make_dataclass("Same", [("y", int)])]),
    ("two lists of one identity", Union[list[str], Annotated[list[str], Min(1)]]),
    ("Literal beside its base type", Union[Literal["a"], str]),
    ("two Annotated ints", Union[Annotated[int, Min(0)], Annotated[int, Min(1)]]),
    # a list identity flattens both discriminator namespaces into one string
    ("list[dataclass A] beside list[enum A]",
     Union[list[make_dataclass("A", [("x", int)])], list[enum_named("A")]]),
    ("list[list[dataclass A]] beside list[list[enum A]]",
     Union[list[list[make_dataclass("A", [("x", int)])]], list[list[enum_named("A")]]]),
]


@pytest.mark.parametrize("annotation", [a for _, a in AMBIGUOUS_SCHEMAS],
                         ids=[label for label, _ in AMBIGUOUS_SCHEMAS])
def test_an_ambiguous_slot_is_refused_at_compile_time(annotation):
    with pytest.raises((TypeError, ValueError)):
        schema_of(annotation)


ADMISSIBLE_HOMONYMS = [
    # a dataclass and an enum of one name sit in different namespaces
    ("dataclass A beside enum A",
     Union[make_dataclass("A", [("x", int)]), enum_named("A")], 2),
    ("date beside a dataclass named date",
     Union[date, make_dataclass("date", [("x", int)])], 2),
    ("str beside a dataclass named str",
     Union[str, make_dataclass("str", [("x", int)])], 2),
    ("list[str] beside a dataclass named list[str]",
     Union[list[str], make_dataclass("list[str]", [("x", int)])], 2),
    ("a dataclass named str, another dataclass, str and date",
     Union[make_dataclass("str", [("x", int)]), SA, str, date], 4),
]


@pytest.mark.parametrize("annotation,count",
                         [(a, c) for _, a, c in ADMISSIBLE_HOMONYMS],
                         ids=[label for label, _, _ in ADMISSIBLE_HOMONYMS])
def test_homonyms_across_the_two_namespaces_stay_admissible(annotation, count):
    """Two discriminators means two namespaces; each option keeps a way in."""
    schema = schema_of(annotation)
    document, nodes = field_slot(schema)
    assert len(nodes) == count
    struct_ids = [n["id"] for n in nodes if n["type"] == "struct"]
    other_ids = [n["id"] for n in nodes if n["type"] != "struct"]
    assert len(set(struct_ids)) == len(struct_ids)
    assert len(set(other_ids)) == len(other_ids)


def test_a_dataclass_named_str_and_a_str_option_are_both_reachable():
    """`$value` is what tells the two dictionary formats apart."""
    Named = make_dataclass("str", [("x", int)])
    schema = schema_of(Union[Named, SA, str, date])
    inline = schema.build(schema.decode({"f": {TYPE: "str", "x": 1}}))
    assert type(inline.f) is Named and inline.f.x == 1
    wrapped = schema.build(schema.decode({"f": {TYPE: "str", VALUE: "hi"}}))
    assert type(wrapped.f) is str and wrapped.f == "hi"
    dated = schema.build(schema.decode({"f": {TYPE: "date", VALUE: "2026-08-08"}}))
    assert dated.f == D


# ---------------------------------------------------------------------------
# to_dict / decode / resolve / build agree
# ---------------------------------------------------------------------------

DEFAULTS = [
    ("str|date str", str | date, "2026-08-08"),
    ("str|date date", str | date, D),
    ("int|float int", int | float, 3),
    ("int|float float", int | float, 3.0),
    ("date|time date", date | time, D),
    ("date|time time", date | time, T),
    ("Role|Status", Role | Status, Status.ADMIN),
    ("str|Role str", str | Role, "ADMIN"),
    ("str|Role enum", str | Role, Role.USER),
    ("Opt[str|date] none", Optional[str | date], None),
    ("list[str]|list[date]", list[str] | list[date], [D]),
    ("list[str]|list[int]", list[str] | list[int], []),
    ("list[str|date]", list[str | date], ["a", D]),
    ("SA|SB", SA | SB, SB("q")),
    ("list[SA|SB]", list[SA | SB], [SA(1), SB("q")]),
    ("W1|W2", W1 | W2, W1(D)),
]


@pytest.mark.parametrize("annotation,value", [(a, v) for _, a, v in DEFAULTS],
                         ids=[label for label, _, _ in DEFAULTS])
def test_a_published_default_is_valid_input_to_the_pipeline(annotation, value):
    schema = schema_of(annotation,
                       field(default_factory=lambda: copy.deepcopy(value)))
    document = schema.to_dict()
    written = document["defs"]["structs"][document["root"]]["fields"][0]["default"]
    written = json.loads(json.dumps(written))
    served = schema.build(schema.decode({}))
    assert exactly_equal(served.f, value)
    restated = schema.build(schema.decode({"f": written}))
    assert exactly_equal(restated.f, value), f"{written!r} -> {restated.f!r}"


def test_nested_defaults_name_their_option_at_every_slot():
    @dataclass
    class Inner:
        v: str | date = D
        n: int | float = 3.0
        xs: list[str] | list[date] = field(default_factory=lambda: [D])
        ys: list[str | date] = field(default_factory=lambda: ["a", D])

    @dataclass
    class Outer:
        a: Inner = field(default_factory=Inner)
        b: Inner | SA = field(default_factory=Inner)

    schema = struct_of(Outer)
    document = schema.to_dict()
    written = {f["name"]: f["default"]
               for f in document["defs"]["structs"]["Outer"]["fields"]}
    assert written["a"] == {"v": {TYPE: "date", VALUE: "2026-08-08"},
                            "n": {TYPE: "float", VALUE: 3.0},
                            "xs": {TYPE: "list[date]", VALUE: ["2026-08-08"]},
                            "ys": [{TYPE: "str", VALUE: "a"},
                                   {TYPE: "date", VALUE: "2026-08-08"}]}
    # the union of dataclasses adds the inline discriminator and nothing else
    assert written["b"][TYPE] == "Inner"
    served = schema.build(schema.decode({}))
    for name in ("a", "b"):
        payload = json.loads(json.dumps(written[name]))
        again = schema.build(schema.decode({name: payload}))
        assert exactly_equal(getattr(again, name), getattr(served, name))


@pytest.mark.parametrize("annotation,values", [(a, v) for _, a, v in MATRIX],
                         ids=MATRIX_IDS)
def test_signature_and_struct_route_unions_identically(annotation, values):
    schema = schema_of(annotation)
    document, nodes = field_slot(schema)

    def take(f):
        return f
    take.__annotations__["f"] = annotation
    sig = signature_of(take)
    assert json.dumps(sig.to_dict()["params"][0]["shape"]) == json.dumps(nodes)

    for value in values:
        wire = json.loads(json.dumps(send(nodes, value, document)))
        built = schema.build(schema.decode({"f": copy.deepcopy(wire)})).f
        kwargs = sig.build(sig.decode({"f": copy.deepcopy(wire)}))
        assert exactly_equal(kwargs["f"], built)


JUNK = [None, True, False, 0, 1, -1, 3.5, "", " ", "x", TYPE, VALUE,
        "2026-08-08", "2026-02-31", "14:30", "ADMIN", "list[str]",
        [], [None], [[]], [{}], {}, {TYPE: "x"}, {VALUE: 1},
        {TYPE: "str", VALUE: "a", "z": 1}, {TYPE: None, VALUE: 1},
        {TYPE: ["str"], VALUE: 1}, {1: 2}, {True: 2},
        {TYPE: "str", VALUE: {TYPE: "str", VALUE: "a"}},
        {"a": {"b": {"c": [1, {TYPE: "date", VALUE: "2026-08-08"}]}}},
        10 ** 400, -(10 ** 400)]


@pytest.mark.parametrize("annotation", [a for _, a, _ in MATRIX], ids=MATRIX_IDS)
def test_resolve_and_build_agree_and_decode_is_total(annotation):
    schema = schema_of(annotation)

    def accepts(call, prepared):
        try:
            call(prepared)
            return True
        except (SchemaTypeError, SchemaValueError, TypeError, ValueError):
            return False

    for wire in JUNK:
        source = {"f": copy.deepcopy(wire)}
        untouched = copy.deepcopy(source)
        prepared = schema.decode(source)          # never raises a schema error
        assert exactly_equal(source, untouched), "decode mutated its input"
        assert accepts(schema.resolve, prepared) == accepts(schema.build, prepared)
        # decoding an already-prepared tree changes nothing further
        assert exactly_equal(schema.decode(copy.deepcopy(prepared)), prepared)


@pytest.mark.parametrize("annotation,values", [(a, v) for _, a, v in MATRIX],
                         ids=MATRIX_IDS)
def test_decode_is_idempotent_on_every_branchs_wire(annotation, values):
    schema = schema_of(annotation)
    document, nodes = field_slot(schema)
    for value in values:
        wire = json.loads(json.dumps(send(nodes, value, document)))
        once = schema.decode({"f": wire})
        twice = schema.decode(copy.deepcopy(once))
        assert exactly_equal(once, twice)
        assert exactly_equal(schema.build(twice).f, value)


@pytest.mark.parametrize("annotation,values", [(a, v) for _, a, v in MATRIX],
                         ids=MATRIX_IDS)
def test_decode_never_hands_back_a_container_from_its_input(annotation, values):
    schema = schema_of(annotation)
    document, nodes = field_slot(schema)
    for value in values:
        wire = json.loads(json.dumps(send(nodes, value, document)))
        source = {"f": wire}
        borrowed: set[int] = set()

        def collect(node):
            if type(node) in (dict, list):
                borrowed.add(id(node))
                for child in (node.values() if type(node) is dict else node):
                    collect(child)

        collect(source)
        prepared = schema.decode(source)

        def check(node):
            if type(node) in (dict, list):
                assert id(node) not in borrowed
                for child in (node.values() if type(node) is dict else node):
                    check(child)

        check(prepared)


def test_an_enum_alias_inside_a_wrapper_resolves_to_its_member():
    schema = schema_of(str | Role)
    built = schema.build(schema.decode({"f": {TYPE: "Role", VALUE: "SUPER"}}))
    assert built.f is Role.ADMIN
    document = schema.to_dict()
    assert document["defs"]["enums"]["Role"]["members"] == ["ADMIN", "USER"]


def test_a_dataclass_instance_inside_a_wrapper_is_refused():
    schema = schema_of(Union[list[SA], list[SB]])
    wire = {TYPE: "list[SA]", VALUE: [SA(1)]}
    with pytest.raises(SchemaTypeError):
        schema.build(schema.decode({"f": wire}))


def test_a_union_inside_a_kept_wrapper_still_decodes():
    schema = schema_of(Union[list[W1], list[str]])
    wire = {TYPE: "list[W1]", VALUE: [{"v": {TYPE: "date", VALUE: "2026-08-08"}}]}
    prepared = schema.decode({"f": copy.deepcopy(wire)})
    assert prepared["f"] == {TYPE: "list[W1]", VALUE: [{"v": D}]}
    assert schema.build(prepared).f == [W1(D)]
    broken = {TYPE: "list[W1]", VALUE: [{"v": {TYPE: "date", VALUE: "2026-02-31"}}]}
    with pytest.raises((SchemaTypeError, SchemaValueError)):
        schema.build(schema.decode({"f": broken}))


def test_a_recursive_union_wraps_at_every_depth():
    schema = struct_of(Node)
    document = schema.to_dict()
    nodes = document["defs"]["structs"]["Node"]["fields"][0]["shape"]
    assert [n["id"] for n in nodes] == ["Node", "str", "date", "None"]
    assert slot_modes(nodes) == ["bare", "wrapper", "wrapper", "bare"]
    deep = {"kid": {"kid": {TYPE: "date", VALUE: "2026-08-08"}}}
    assert schema.build(schema.decode(deep)) == Node(kid=Node(kid=D))
    unreachable = {"kid": {TYPE: "date", VALUE: "2026-02-31"}}
    with pytest.raises((SchemaTypeError, SchemaValueError)):
        schema.build(schema.decode(unreachable))


# ---------------------------------------------------------------------------
# Generated shapes: the same properties, over shapes nobody wrote by hand
# ---------------------------------------------------------------------------

LEAVES = [str, int, float, bool, date, time, Role, Status, Level, Tag,
          SA, SB, W1, W4, Literal["a", "b"], Literal[1, 2],
          Annotated[int, Min(0)], Annotated[date, Min(date(2000, 1, 1))]]


def _generate(rng, depth):
    if depth > 0 and rng.random() < 0.35:
        return list[_generate_union(rng, depth - 1)]
    return rng.choice(LEAVES)


def _generate_union(rng, depth):
    options = [_generate(rng, depth) for _ in range(rng.randint(1, 4))]
    if rng.random() < 0.2:
        options.append(None)
    return options[0] if len(options) == 1 else Union[tuple(options)]


def _document_slots(nodes, document, seen):
    yield nodes
    for node in nodes:
        if node["type"] == "list":
            yield from _document_slots(node["item"], document, seen)
        elif node["type"] == "struct" and node["ref"] not in seen:
            seen.add(node["ref"])
            for f in document["defs"]["structs"][node["ref"]]["fields"]:
                yield from _document_slots(f["shape"], document, seen)


def _shape_slots(shapes):
    yield tuple(shapes)
    for shape in shapes:
        if type(shape) is ListShape:
            yield from _shape_slots(shape.item)
        elif type(shape) is StructShape:
            for f in shape.fields:
                yield from _shape_slots(f.shape)


def _sample(node, document, rng):
    kind = node["type"]
    if kind == "str":
        return rng.choice(node["choices"]) if "choices" in node else "s"
    if kind == "int":
        return rng.choice(node["choices"]) if "choices" in node else 4
    if kind == "float":
        return 4.5
    if kind == "bool":
        return rng.choice([True, False])
    if kind == "date":
        return date(2026, 8, rng.randint(1, 28))
    if kind == "time":
        return time(rng.randint(0, 23), 30)
    if kind == "none":
        return None
    if kind == "list":
        return [_sample(rng.choice(node["item"]), document, rng)
                for _ in range(rng.randint(0, 2))]
    if kind == "enum":
        return rng.choice(list(node_pytype(node, document)))
    definition = document["defs"]["structs"][node["ref"]]
    cls = node_pytype(node, document)
    return cls(**{f["name"]: _sample(rng.choice(f["shape"]), document, rng)
                  for f in definition["fields"]})


REFUSALS = ("duplicate option types", "duplicate discriminator name",
            "both compile to", "must be accompanied by another option",
            "metadata on a union of multiple types")


def _exercise(annotation):
    """Every property above, on one generated shape. Returns False if refused."""
    try:
        schema = schema_of(annotation)
    except (TypeError, ValueError) as error:
        assert any(text in str(error) for text in REFUSALS), str(error)
        return False

    document, nodes = field_slot(schema)
    rng = random.Random(len(json.dumps(document)))

    # the document's wrapper rule is the decoder's, at every slot
    shape_slots = list(_shape_slots(schema.fields[0].shape))
    doc_slots = list(_document_slots(nodes, document, set()))
    if len(shape_slots) == len(doc_slots):
        for shapes, slot in zip(shape_slots, doc_slots):
            portable = _portable_options(shapes)
            modes = slot_modes(slot)
            for index, (node, shape) in enumerate(zip(slot, shapes)):
                if node["type"] == "struct":
                    continue
                assert (modes[index] == "wrapper") == any(
                    shape is option for option in portable)

    # no legal slot carries an ambiguous identity
    for slot in doc_slots:
        if len(slot) < 2:
            continue
        struct_ids = [n["id"] for n in slot if n["type"] == "struct"]
        other_ids = [n["id"] for n in slot if n["type"] != "struct"]
        assert len(set(struct_ids)) == len(struct_ids)
        assert len(set(other_ids)) == len(other_ids)

    # every branch round-trips, and no branch smuggles another's payload
    samples = []
    for index, node in enumerate(nodes):
        value = _sample(node, document, rng)
        samples.append((index, value))
        if slot_branches(nodes, value, document)[:1] != [index]:
            continue                      # genuinely ambiguous; nothing to assert
        wire = json.loads(json.dumps(send(nodes, value, document, branch=index)))
        state, result, _ = outcome(schema, wire)
        assert state == "ok", f"{annotation}: {value!r} via {wire!r}: {result}"
        assert exactly_equal(result, value), f"{annotation}: {wire!r} -> {result!r}"

    modes = slot_modes(nodes)
    for index, node in enumerate(nodes):
        if modes[index] != "wrapper":
            continue
        for other, value in samples:
            if other == index:
                continue
            try:
                payload = json.loads(json.dumps(write_node(nodes[other], value,
                                                           document)))
            except (TypeError, ValueError, AssertionError):
                continue
            state, result, _ = outcome(schema, {TYPE: node["id"], VALUE: payload})
            assert state == "refused" or node_accepts(node, result, document), (
                f"{annotation}: $type={node['id']!r} carrying {payload!r} "
                f"became {result!r}")
    return True


@pytest.mark.parametrize("seed", range(24))
def test_generated_union_shapes_hold_every_property(seed):
    rng = random.Random(seed)
    compiled = 0
    for _ in range(25):
        if _exercise(_generate_union(rng, 2)):
            compiled += 1
    assert compiled, "the generator produced nothing compilable"


@settings(max_examples=60, deadline=None,
          suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much])
@given(st.integers(min_value=0, max_value=10 ** 6))
def test_generated_union_shapes_hold_every_property_hypothesis(seed):
    _exercise(_generate_union(random.Random(seed), 2))


# ---------------------------------------------------------------------------
# Known defects (agent D findings). Both are latent rather than unsound, so they
# are pinned here rather than left as prose.
# ---------------------------------------------------------------------------

def test_an_unknown_type_says_which_namespace_the_name_belongs_to():
    """D-1, fixed: the refusal no longer denies an identity `to_dict` publishes.

    In a slot with two or more dataclass options and two or more options sharing
    a portable spelling, a wrapper whose payload missed its option arrives here
    still a dict. Offering only the dataclass names read as "there is no such
    option", when the very same identity is accepted one call earlier with a
    payload that parses. A note now says which namespace the name belongs to.
    """
    schema = schema_of(Union[SA, SB, str, date])
    # the identity is real: with a payload that decodes, this very wire works
    assert schema.build(schema.decode(
        {"f": {TYPE: "date", VALUE: "2026-08-08"}})).f == D
    with pytest.raises(SchemaValueError) as caught:
        schema.build(schema.decode({"f": {TYPE: "date", VALUE: "2026-02-31"}}))
    error = caught.value
    offered = str(error).split("expected one of")[1]
    diagnosable = "date" in offered or any(
        "date" in note for note in getattr(error, "__notes__", ()))
    assert diagnosable, f"{error} / notes={getattr(error, '__notes__', [])}"


def test_option_notes_survive_the_coordinates_they_travel_through():
    Inner = make_dataclass("Inner", [("xs", list[int] | list[str])])
    with pytest.raises(SchemaValueError) as caught:
        struct_of(Inner)._check(Inner(xs=["a", 1.5]))
    assert caught.value.leaf == "matches no option: list[int] | list[str]"
    assert getattr(caught.value, "__notes__", []) == [
        "as list[int]: [0]: expected int, got str",
        "as list[str]: [1]: expected str, got float"]


def test_option_notes_survive_default_certification():
    with pytest.raises((TypeError, ValueError)) as caught:
        struct_of(make_dataclass("Certified", [
            ("xs", list[int] | list[str],
             field(default_factory=lambda: ["a", 1.5]))]))
    assert getattr(caught.value, "__notes__", []) == [
        "as list[int]: [0]: expected int, got str",
        "as list[str]: [1]: expected str, got float"]


def test_the_notes_do_exist_before_they_are_prefixed():
    """Pins where D-3 actually loses them: the diagnosis is built, then dropped."""
    from pytypehint import Int
    from pytypehint.validation import check_options_value
    shapes = (ListShape(item=(Int(),)), ListShape(item=(Str(),)))
    with pytest.raises(SchemaValueError) as caught:
        check_options_value(shapes, ["a", 1.5])
    assert getattr(caught.value, "__notes__", []) == [
        "as list[int]: [0]: expected int, got str",
        "as list[str]: [1]: expected str, got float"]


def test_a_list_rejects_items_that_share_one_identity():
    """D-2, fixed: `List` is public API, so it applies the rule to its own items.

    An enum class named `str` beside a `str` publishes two options answering to
    one `$type`. It used to be constructible standalone and inert, caught only
    when a `Field` was built around it; the rule now runs where the two
    identities actually sit.
    """
    with pytest.raises(ValueError, match=r"List\.item: duplicate discriminator"):
        List(item=(Str(), EnumShape(cls=Enum("str", {"A": "a"}))))


def test_the_rule_reaches_every_depth_a_list_can_be_nested_to():
    """The shape that holds the collision is refused wherever it is built.

    No ambiguous list can be handed to a field any more, because none can be
    made — so this walks the constructions that used to smuggle one in and
    checks each is refused on its own.
    """
    homonym = EnumShape(cls=Enum("str", {"A": "a"}))
    assert [Str().option_id(), homonym.option_id()] == ["str", "str"]

    with pytest.raises(ValueError, match=r"List\.item: duplicate discriminator"):
        List(item=(Str(), homonym))
    with pytest.raises(ValueError, match=r"List\.item: duplicate discriminator"):
        List(item=(List(item=(Str(), homonym)),))
    with pytest.raises(ValueError, match=r"Field 'f': duplicate discriminator"):
        Field(name="f", shape=(Str(), homonym))

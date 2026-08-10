"""Adversarial hardening of `to_dict()` — the portable contract as data.

The rule under attack: if `struct_of()` or `signature_of()` accepts a schema,
`to_dict()` must not fail, must not leak anything outside the portable
vocabulary, and must produce the same bytes in any process. Everything here is
reduced from a reproduction; the divergences from docs/contract.md that this file
was written to record are all closed, and each test still names the promise it
was raised against.
"""
import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field, make_dataclass
from datetime import date, time
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional, Union

import pytest

from pytypehint import (
    Choices, Description, Extra, Field, FileHint, IsPassword, Label, Max, Min,
    MultipleOf, OptionalToggle, Pattern, Placeholder, Rows, Signature, Slider,
    Step, signature_of, struct_of,
)

PRIMITIVES = (dict, list, str, int, float, bool, type(None))


# ---------------------------------------------------------------------------
# Walking helpers
# ---------------------------------------------------------------------------

def walk(node, path=()):
    """Every value in a document, containers included, with its path."""
    yield path, node
    if type(node) is dict:
        for key, value in node.items():
            yield from walk(value, (*path, key))
    elif type(node) is list:
        for i, value in enumerate(node):
            yield from walk(value, (*path, i))


def containers(document):
    return [id(value) for _, value in walk(document)
            if type(value) in (dict, list)]


def destroy(node):
    """Mutate every container in the tree as destructively as possible."""
    if type(node) is dict:
        for value in list(node.values()):
            destroy(value)
        node.clear()
        node["$poison"] = ["gone"]
    elif type(node) is list:
        for value in list(node):
            destroy(value)
        node.clear()
        node.append({"poison": 1})


# ---------------------------------------------------------------------------
# The subjects: one deterministic document per index, shared with subprocesses
# ---------------------------------------------------------------------------

class Role(Enum):
    ADMIN = 1
    USER = 2


def _enum(name: str, members: dict) -> type[Enum]:
    """Built through a helper so the class name can differ from the binding."""
    return Enum(name, members)      # type: ignore[return-value]


Namesake = _enum("Role", {"A": "B", "B": "A"})      # a homonym of Role
Ordinal = _enum("Role#2", {"Z": (1, [2])})          # unportable member values


@dataclass
class Leaf:
    n: Annotated[int, Min(0), Max(10), MultipleOf(5), Step(5),
                 Slider(show_value=False), Placeholder("n")] = 5


@dataclass
class Recursive:
    kid: Optional["Recursive"] = None
    kids: list["Recursive"] = field(default_factory=list)


@dataclass
class MutualA:
    b: Optional["MutualB"] = None


@dataclass
class MutualB:
    a: Optional[MutualA] = None
    many: list[MutualA] = field(default_factory=list)


@dataclass
class Sink:
    """Every documented key that can sit in one dataclass."""
    numbers: Union[int, float] = 3
    when: Union[str, date] = date(2024, 6, 1)
    days: list[Union[str, date]] = field(
        default_factory=lambda: [date(2024, 6, 1)])
    either: Union[list[int], list[str]] = field(default_factory=list)
    role: Optional[Role] = Role.ADMIN
    leaf: Leaf = field(default_factory=Leaf)
    text: Annotated[str, Min(1), Max(20), Pattern("[a-z]+", message="lower"),
                    IsPassword(), Rows(4), Placeholder("t"),
                    Extra("z.last", ""), Extra("a.first", "1")] = "abc"
    clock: Annotated[time, Min(time(9, 0, 0), exclusive=True),
                     Max(time(18, 0, 0)),
                     Choices(values=(time(12, 0, 0),))] = time(12, 0, 0)
    flag: Annotated[Optional[bool], Label("F"), Description("d"),
                    OptionalToggle(False)] = None


def _homonyms():
    """Three classes of one name, one of them already wearing an ordinal."""
    first = make_dataclass("T", [("x", int)])
    ordinal = make_dataclass("T#2", [("y", str)])
    second = make_dataclass("T", [("z", bool)])
    third = make_dataclass("T", [("w", Optional[bool])])
    return make_dataclass("Holder", [
        ("a", first), ("b", ordinal), ("c", second), ("d", third),
        ("e", list[first]), ("f", Union[first, ordinal])])


def _hostile_names():
    """Class names no source file could spell, next to the shapes they shadow."""
    named_int = make_dataclass("int", [("x", int)])
    named_list = make_dataclass("list[str]", [("x", int)])
    named_type = make_dataclass("$type", [("x", int)])
    named_empty = make_dataclass("", [("x", int)])
    return make_dataclass("Hostile", [
        ("a", Union[named_int, int]),
        ("b", Union[named_list, list[str]]),
        ("c", named_type),
        ("d", named_empty),
    ])


def _enum_homonyms():
    return make_dataclass("Enums", [
        ("a", Role), ("b", Namesake), ("c", Ordinal),
        ("d", list[Role]), ("e", Union[Role, int]),
    ])


def _signature():
    def upload(name: Annotated[str, Label("N")],
               role: Role = Role.USER,
               sink: Optional[Sink] = None,
               tags: list[Union[int, float]] = [1, 2.0]):
        """Upload a document."""

    return signature_of(upload)


SUBJECTS = [
    lambda: struct_of(Sink),
    lambda: struct_of(Leaf),
    lambda: struct_of(Recursive),
    lambda: struct_of(MutualA),
    lambda: struct_of(MutualB),
    lambda: struct_of(_homonyms()),
    lambda: struct_of(_hostile_names()),
    lambda: struct_of(_enum_homonyms()),
    _signature,
]


def documents():
    return [subject().to_dict() for subject in SUBJECTS]


def serialise():
    """What a subprocess prints, byte for byte, with no sort_keys anywhere."""
    return json.dumps(documents(), ensure_ascii=False)


# ===========================================================================
# Findings still open
# ===========================================================================

def test_writing_a_document_never_reads_the_filesystem():
    # `FileHint` states a file's contract and never asks the world about it, so a
    # default may name a path that exists nowhere: compiling the schema and
    # writing its document are both indifferent to what is on disk. If they were
    # not, one definition would write one document while a file existed and
    # another after it was deleted.
    schema = struct_of(make_dataclass("Paths", [
        ("files", Union[list[Annotated[str, FileHint(extensions=(".pdf",))]],
                        list[int]],
         field(default_factory=lambda: ["nowhere/at/all/doc.pdf"]))]))

    seen: list = []
    real = Path.stat
    Path.stat = lambda self, *a, **k: (seen.append(str(self)),
                                       real(self, *a, **k))[1]
    try:
        document = schema.to_dict()
    finally:
        Path.stat = real

    assert seen == []
    assert document["defs"]["structs"]["Paths"]["fields"][0]["default"] == {
        "$type": "list[str]", "$value": ["nowhere/at/all/doc.pdf"]}
    assert schema.to_dict() == document


def test_every_accepted_schema_writes_strict_json():
    for bad in (float("inf"), float("nan")):
        try:
            schema = struct_of(make_dataclass(
                "H", [("x", Annotated[float, Step(bad)])]))
        except ValueError:
            continue                    # the atom refused it: nothing to write
        json.dumps(schema.to_dict(), allow_nan=False)


def test_a_document_always_survives_its_own_json_round_trip():
    try:
        schema = struct_of(make_dataclass(
            "H", [("x", Annotated[float, Step(float("nan"))])]))
    except ValueError:
        return
    document = schema.to_dict()
    assert json.loads(json.dumps(document)) == document


# ===========================================================================
# Boundaries: behaviour a reader has to know about, pinned
# ===========================================================================

def test_two_thousand_namesakes_still_get_unique_ids():
    # `_identify` rescans from ordinal 2 for every namesake, which is quadratic
    # in the number of classes sharing a name (measured: 200 -> 4 ms, 1600 ->
    # 234 ms, 3200 -> 1232 ms). The ids it produces are correct, and that is
    # what a reader depends on; this pins the correctness at a size where the
    # cost is visible.
    kids = [make_dataclass("T", [("x", int)]) for _ in range(2000)]
    holder = make_dataclass("Holder", [(f"f{i}", kid)
                                       for i, kid in enumerate(kids)])
    table = struct_of(holder).to_dict()["defs"]["structs"]

    ids = list(table)
    assert len(set(ids)) == len(ids)
    assert ids[-1] == "T#2000"
    assert {value["name"] for value in table.values()} == {"Holder", "T"}


@pytest.mark.parametrize("order,expected", [
    ("T,T#2,T,T", ["T", "T#2", "T#3", "T#4"]),
    ("T#2,T,T,T", ["T#2", "T", "T#3", "T#4"]),
    ("T,T,T#2,T", ["T", "T#2", "T#2#2", "T#3"]),
])
def test_a_class_whose_name_already_wears_an_ordinal_never_steals_an_id(
        order, expected):
    classes = [make_dataclass(name, [(f"f{i}", int)])
               for i, name in enumerate(order.split(","))]
    holder = make_dataclass("Holder", [(f"g{i}", cls)
                                       for i, cls in enumerate(classes)])
    ids = list(struct_of(holder).to_dict()["defs"]["structs"])

    assert ids[1:] == expected
    assert len(set(ids)) == len(ids)


def test_two_compilations_of_one_class_in_a_hand_built_signature():
    # `struct_of` caches per call, so a shared dataclass is one Struct and one
    # definition. Two calls give two Struct objects, and a hand-assembled
    # Signature can hold both: the emitter keys definitions by Struct identity,
    # not by class, because two hand-built Structs of one class may carry
    # different fields and merging them would drop one. The invariants a reader
    # relies on survive it — distinct ids, one name, every ref resolvable.
    first, second = struct_of(Leaf), struct_of(Leaf)
    assert first is not second

    document = Signature(name="f", params=(
        Field(name="p", shape=(first,)),
        Field(name="q", shape=(second,)))).to_dict()

    table = document["defs"]["structs"]
    refs = [param["shape"][0]["ref"] for param in document["params"]]
    assert refs == ["Leaf", "Leaf#2"]
    assert all(ref in table for ref in refs)
    assert {value["name"] for value in table.values()} == {"Leaf"}


def test_a_docstring_that_is_empty_is_present_and_empty():
    # Three states, not two: no docstring omits the key, an empty docstring is
    # a docstring and writes "", and `python -OO` removes every docstring — the
    # caveat contract.md states. Every other string in the format is non-empty
    # by construction, so this is the one place a reader meets "".
    def absent(x: int):
        pass

    def empty(x: int):
        ""

    def present(x: int):
        "text"

    assert "doc" not in signature_of(absent).to_dict()
    assert signature_of(empty).to_dict()["doc"] == ""
    assert signature_of(present).to_dict()["doc"] == "text"


def test_the_documented_docstring_caveat_is_the_only_thing_minus_oo_changes():
    code = ("import json\n"
            "from pytypehint import signature_of\n"
            "def f(x: int):\n"
            "    'the doc'\n"
            "print(json.dumps(signature_of(f).to_dict()))\n")
    plain = json.loads(_child([], code))
    stripped = json.loads(_child(["-OO"], code))

    assert plain.pop("doc") == "the doc"
    assert "doc" not in stripped
    assert plain == stripped


# ===========================================================================
# The properties the attacks could not break
# ===========================================================================

def _child(flags, code, env_extra=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [p for p in sys.path if p] + [env.get("PYTHONPATH", "")])
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(env_extra or {})
    result = subprocess.run([sys.executable, *flags, "-c", code],
                            capture_output=True, env=env)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    return result.stdout


CHILD = ("import json, sys\n"
         "sys.path.insert(0, {folder!r})\n"
         "import test_hardening_c as subject\n"
         "sys.stdout.write(subject.serialise())\n")


@pytest.mark.parametrize("hash_seed", ["0", "1", "4294967295", "random"])
def test_a_document_is_the_same_bytes_in_another_process_under_any_hash_seed(
        hash_seed):
    code = CHILD.format(folder=os.path.dirname(os.path.abspath(__file__)))
    written = _child([], code, {"PYTHONHASHSEED": hash_seed})

    assert written == serialise().encode("utf-8")


def test_nothing_in_the_document_is_outside_the_portable_vocabulary():
    for document in documents():
        for path, value in walk(document):
            assert type(value) in PRIMITIVES, (path, value)
            if type(value) is dict:
                assert all(type(key) is str for key in value), path
        # bool is not int here: a reader that switches on the JSON type must not
        # meet `true` where the format spells a number.
        for path, value in walk(document):
            if path and path[-1] in ("min_length", "max_length", "rows",
                                    "multiple_of", "min_items", "max_items",
                                    "min_size", "max_size", "v"):
                assert type(value) is int and type(value) is not bool, path
            if path and path[-1] in ("exclusive_min", "exclusive_max",
                                     "is_password", "optional_toggle",
                                     "show_value"):
                assert type(value) is bool, path


def test_no_implementation_object_reaches_the_document():
    text = json.dumps(documents(), ensure_ascii=False)
    for leak in ("object at 0x", "<class ", "Struct(", "Field(", "re.compile",
                 "_Factory", "MISSING", "<enum ", "Int(", "Placeholder("):
        assert leak not in text, leak


def test_destroying_a_document_at_every_depth_leaves_the_next_call_intact():
    for subject in SUBJECTS:
        schema = subject()
        first = schema.to_dict()
        original = json.loads(json.dumps(first))

        destroy(first)
        assert schema.to_dict() == original


def test_two_calls_share_no_container_at_any_depth():
    for subject in SUBJECTS:
        schema = subject()
        first, second = schema.to_dict(), schema.to_dict()
        left, right = containers(first), containers(second)

        assert not set(left) & set(right)
        assert len(set(left)) == len(left)


def test_every_reference_resolves_and_the_root_is_a_definition():
    for document in documents():
        structs = document["defs"]["structs"]
        enums = document["defs"]["enums"]
        if document["kind"] == "struct":
            assert document["root"] in structs
        for path, value in walk(document):
            if type(value) is dict and "ref" in value:
                table = structs if value["type"] == "struct" else enums
                assert value["ref"] in table, path


def test_a_written_default_is_valid_input_to_the_pipeline():
    schema = struct_of(Sink)
    fields = schema.to_dict()["defs"]["structs"]["Sink"]["fields"]
    written = {f["name"]: f["default"] for f in fields}

    # the document's own defaults, through decode and build, with no translation
    assert schema.build(schema.decode(written)) == schema.build({})
    assert schema.build(schema.decode(json.loads(json.dumps(written)))) \
        == schema.build({})


def test_the_emitter_never_needs_more_stack_than_the_compiler():
    # A schema `struct_of` accepts must be writable at the same recursion
    # limit; an emitter that recurses deeper would crash on schemas the core
    # takes. Measured per shape that nests: a list of lists and a chain of
    # dataclasses.
    nested = int
    for _ in range(40):
        nested = list[nested]
    chained = int
    for i in range(40):
        chained = make_dataclass(f"C{i}", [("x", chained)])

    original = sys.getrecursionlimit()
    try:
        for hint in (nested, chained):
            holder = make_dataclass("Holder", [("x", hint)])
            compiling = _minimum_limit(lambda: struct_of(holder))
            schema = struct_of(holder)
            emitting = _minimum_limit(schema.to_dict)

            assert emitting <= compiling, (emitting, compiling)
    finally:
        sys.setrecursionlimit(original)


def _minimum_limit(call, ceiling=20000):
    low, high = 20, ceiling
    while low < high:
        middle = (low + high) // 2
        try:
            sys.setrecursionlimit(middle)
            call()
        except RecursionError:
            low = middle + 1
        else:
            high = middle
        finally:
            sys.setrecursionlimit(ceiling)
    return low


def test_eight_threads_on_one_schema_get_equal_documents_and_share_nothing():
    schema = struct_of(Sink)
    collected: list = []
    lock = threading.Lock()

    def worker():
        mine = [schema.to_dict() for _ in range(40)]
        with lock:
            collected.extend(mine)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len({json.dumps(document) for document in collected}) == 1
    every = [i for document in collected for i in containers(document)]
    assert len(set(every)) == len(every)


@pytest.mark.parametrize("hostile", [
    chr(0xd800),                      # a lone surrogate
    "a" + chr(0) + "b",               # a NUL
    chr(0x202e),                      # a bidi override
    chr(0xfeff) + chr(0x200b),        # a BOM and a zero-width space
    chr(0x1f600) * 100,               # astral plane
])
def test_a_hostile_author_string_still_serialises_and_round_trips(hostile):
    schema = struct_of(make_dataclass("H", [
        ("x", Annotated[str, Placeholder(hostile), Extra("pkg.k", hostile)])]))
    document = schema.to_dict()

    text = json.dumps(document)          # ensure_ascii keeps it transportable
    text.encode("utf-8")
    assert json.loads(text) == document
    node = document["defs"]["structs"]["H"]["fields"][0]["shape"][0]
    assert node["placeholder"] == hostile
    assert node["extras"] == {"pkg.k": hostile}


def test_a_giant_default_and_a_dense_dag_stay_linear_and_portable():
    # 2**24 paths through 24 classes, and a default of 50k items: the document
    # is written once per definition and once per value, not once per path.
    level = None
    for i in range(24):
        annotations = ({"a": level, "b": level} if level is not None
                       else {"a": int, "b": int})
        level = make_dataclass(f"L{i}", list(annotations.items()))
    document = struct_of(level).to_dict()
    assert len(document["defs"]["structs"]) == 24

    big = make_dataclass("Big", [
        ("xs", list[int], field(default_factory=lambda: list(range(50000))))])
    written = struct_of(big).to_dict()
    default = written["defs"]["structs"]["Big"]["fields"][0]["default"]
    assert default == list(range(50000))
    assert json.loads(json.dumps(written)) == written

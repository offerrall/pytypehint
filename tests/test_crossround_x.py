"""Numeric exactness and emitter determinism, attacked from the outside.

Three promises are under test here, all of them about the same seam — the point
where a number or an option crosses between the schema, the portable tree and the
document.

`decode` restores a float written without its fraction and invents nothing else:
an integer that no float equals is not a float that lost its fraction, so it is
handed back for validation to report. The frontier is exactness, not size, and it
is symmetric — `2**60` and `2**200` are floats written whole and must come back as
floats, while `2**53 + 1` and `-(2**53) - 1` must not.

The emitter publishes the bound the schema enforces, not the float next door.

The emitter is deterministic and total: choosing which option a default inhabits
reads the schema and the value alone, so `to_dict()` writes the same bytes in
every process and never fails on a schema the core accepted. No check in the core
consults the world — not the filesystem, not the working directory — so there is
no seam left through which a document could depend on where or when it was
written, and none through which two equal definitions could disagree — the signed
zero that used to make one bound write two documents is normalized on the way
out.
"""

import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass, field, make_dataclass
from typing import Annotated

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pytypehint import (
    Bool, Choices, Extra, Field, FileHint, Float, Int, List, Max, Min, Pattern,
    Placeholder, Rows, Step, Str, Struct, struct_of,
)
from pytypehint.contract import _Document, _shape_node
from pytypehint.validation import value_branch

# ---------------------------------------------------------------------------
# The representability frontier
# ---------------------------------------------------------------------------

# Integers that some float equals exactly, and integers that none does. Written
# out rather than computed so the two lists say which is which, and mirrored to
# the negative side because a sign must not change the answer.
# Above 2**54 the spacing is 4, not 2, so `2**54 + 4` is the first integer past
# the power that a float still equals.
_EXACT = [0, 1, 2, 2**52, 2**52 + 1, 2**53 - 1, 2**53, 2**53 + 2, 2**54,
          2**54 + 4, 2**60, 2**63, 2**64, 10**15, 10**16, 10**22, 2**200,
          2**1023]
_INEXACT = [2**53 + 1, 2**53 + 3, 2**54 + 1, 2**54 + 3, 2**63 + 1, 2**64 + 1,
            10**23, 10**24, 2**200 + 1, 2**1023 + 1,
            # Beyond the float range there is nothing to be exact about: these
            # take the OverflowError road to the same answer.
            2**1024, 10**400, 10**1000]

_BOTH_SIGNS = ([(v, True) for v in _EXACT] + [(-v, True) for v in _EXACT]
               + [(v, False) for v in _INEXACT] + [(-v, False) for v in _INEXACT])


def _exactly_representable(value: int) -> bool:
    try:
        return float(value) == value
    except OverflowError:
        return False


def test_the_frontier_table_says_what_it_claims():
    """The table is the premise of every test below, so it is checked first."""
    for value, exact in _BOTH_SIGNS:
        assert _exactly_representable(value) is exact, value


@dataclass
class _Whole:
    x: float = 0.0


@pytest.mark.parametrize("value,exact", _BOTH_SIGNS,
                         ids=[f"{'exact' if e else 'inexact'}:{v:+d}"[:40]
                              for v, e in _BOTH_SIGNS])
def test_decode_restores_exactly_the_integers_a_float_equals(value, exact):
    """A float written without its fraction comes back; anything else stands."""
    restored = struct_of(_Whole).decode({"x": value})["x"]
    if exact:
        assert type(restored) is float
        assert restored == value
    else:
        assert type(restored) is int
        assert restored == value


@pytest.mark.parametrize("value,exact", _BOTH_SIGNS,
                         ids=[f"{'exact' if e else 'inexact'}:{v:+d}"[:40]
                              for v, e in _BOTH_SIGNS])
def test_decode_and_build_never_disagree_at_the_frontier(value, exact):
    """What decode prepares, build takes; what decode leaves, build refuses."""
    schema = struct_of(_Whole)
    prepared = schema.decode({"x": value})
    if exact:
        assert schema.build(prepared).x == value
    else:
        with pytest.raises(Exception, match="expected float, got int"):
            schema.build(prepared)


@dataclass
class _Inner:
    y: float = 0.0


@dataclass
class _Deep:
    a: list[float] = field(default_factory=list)
    b: list[list[float]] = field(default_factory=list)
    c: _Inner = field(default_factory=_Inner)
    d: Annotated[float, Min(-(10**30)), Max(10**30)] = 0.0


@pytest.mark.parametrize("value,exact", _BOTH_SIGNS,
                         ids=[f"{'exact' if e else 'inexact'}:{v:+d}"[:40]
                              for v, e in _BOTH_SIGNS])
def test_the_frontier_is_the_same_at_every_depth(value, exact):
    """A list item, a nested item, a field of a nested dataclass, a bounded field."""
    decoded = struct_of(_Deep).decode(
        {"a": [value], "b": [[value]], "c": {"y": value}, "d": value})
    reached = (decoded["a"][0], decoded["b"][0][0], decoded["c"]["y"], decoded["d"])
    expected = float if exact else int
    assert [type(v) for v in reached] == [expected] * 4
    assert all(v == value for v in reached)


@dataclass
class _Ambiguous:
    v: float | int = 0.0


@pytest.mark.parametrize("value,exact", _BOTH_SIGNS,
                         ids=[f"{'exact' if e else 'inexact'}:{v:+d}"[:40]
                              for v, e in _BOTH_SIGNS])
def test_a_float_wrapper_is_consumed_only_with_the_number_it_names(value, exact):
    """The wrapper names an option; a payload that never reached it keeps it."""
    schema = struct_of(_Ambiguous)
    decoded = schema.decode({"v": {"$type": "float", "$value": value}})
    if exact:
        assert type(decoded["v"]) is float and decoded["v"] == value
        assert schema.build(decoded).v == value
    else:
        # Unconsumed, so validation reports it rather than an invented float
        # settling silently under the option the wrapper named.
        assert decoded["v"] == {"$type": "float", "$value": value}
        with pytest.raises(Exception):
            schema.build(decoded)


@pytest.mark.parametrize("value,exact", _BOTH_SIGNS,
                         ids=[f"{'exact' if e else 'inexact'}:{v:+d}"[:40]
                              for v, e in _BOTH_SIGNS])
def test_an_int_wrapper_hands_its_integer_through_untouched(value, exact):
    """The `int` option of the same slot is unaffected by any of this."""
    decoded = struct_of(_Ambiguous).decode({"v": {"$type": "int", "$value": value}})
    assert type(decoded["v"]) is int and decoded["v"] == value
    assert struct_of(_Ambiguous).build(decoded).v == value
    assert exact in (True, False)


@settings(max_examples=400, deadline=None, derandomize=True)
@given(st.integers(min_value=-(2**400), max_value=2**400))
def test_decode_restores_an_integer_exactly_when_a_float_equals_it(value):
    """The rule holds for integers nobody picked by hand. derandomize: one seed."""
    schema = struct_of(_Whole)
    restored = schema.decode({"x": value})["x"]
    if _exactly_representable(value):
        assert type(restored) is float and restored == value
        assert schema.build({"x": restored}).x == value
    else:
        assert type(restored) is int and restored == value


# ---------------------------------------------------------------------------
# The bound the document publishes is the bound the schema enforces
# ---------------------------------------------------------------------------

def _float_node(**atoms) -> dict:
    schema = struct_of(make_dataclass(
        "_B", [("x", Annotated[tuple([float, *atoms.values()])])]))
    return schema.to_dict()["defs"]["structs"]["_B"]["fields"][0]["shape"][0]


def _float_bytes(**atoms) -> str:
    schema = Struct(cls=make_dataclass("_C", [("x", float)]),
                    fields=(Field(name="x", shape=(Float(**atoms),)),))
    return json.dumps(schema.to_dict())


@pytest.mark.parametrize("value", _EXACT + [-v for v in _EXACT])
def test_a_bound_with_a_float_twin_is_published_as_that_float(value):
    """`Min(0)` and `Min(0.0)` are one atom, so a float shape writes both as one."""
    node = _float_node(min=Min(value))
    assert type(node["min"]) is float
    assert node["min"] == value


@pytest.mark.parametrize("value", [2**53 + 1, -(2**53) - 1, 2**54 + 1,
                                   -(2**54) - 1, 10**23, -(10**23), 2**200 + 1])
def test_a_bound_no_float_equals_is_published_as_written(value):
    """Publishing the neighbour would state a bound the schema does not hold."""
    for atom, key in ((Min, "min"), (Max, "max")):
        node = _float_node(**{key: atom(value)})
        assert type(node[key]) is int
        assert node[key] == value


_BOUNDS = [v for v in (_EXACT + [-v for v in _EXACT]
                       + [2**53 + 1, -(2**53) - 1, 2**54 + 1, 10**23, 2**200 + 1])
           if abs(v) < 2**1000]


@pytest.mark.parametrize("value", _BOUNDS)
@pytest.mark.parametrize("key", ["min", "max"])
@pytest.mark.parametrize("exclusive", [False, True], ids=["inclusive", "exclusive"])
def test_the_published_bound_and_the_enforced_bound_agree_both_ways(
        value, key, exclusive):
    """No float the document permits is refused, and none it forbids is taken."""
    atom = (Min if key == "min" else Max)(value, exclusive=exclusive)
    shape = _float_node(**{key: atom})[key]
    schema = struct_of(make_dataclass(
        "_B", [("x", Annotated[float, atom])]))
    published = shape
    edge = float(published)
    for candidate in (edge, math.nextafter(edge, math.inf),
                      math.nextafter(edge, -math.inf)):
        if not math.isfinite(candidate):
            continue
        if key == "min":
            permitted = candidate > published if exclusive else candidate >= published
        else:
            permitted = candidate < published if exclusive else candidate <= published
        try:
            schema.resolve({"x": candidate})
            accepted = True
        except Exception:
            accepted = False
        assert permitted is accepted, (published, candidate)


@pytest.mark.parametrize("value", _BOUNDS)
def test_a_published_bound_survives_json_unchanged(value):
    """An int bound stays an int and a float bound stays a float through JSON."""
    node = _float_node(min=Min(value))
    assert json.loads(json.dumps(node["min"])) == node["min"]
    assert type(json.loads(json.dumps(node["min"]))) is type(node["min"])


@pytest.mark.parametrize("value", [v for v in _BOUNDS if v > 0])
def test_a_float_step_is_published_exactly_or_not_at_all(value):
    """A step sits beside the bounds and is held to the same exactness."""
    node = _float_node(step=Step(value))
    assert node["step"] == value
    assert type(node["step"]) is (float if _exactly_representable(value) else int)


@pytest.mark.parametrize("value", _BOUNDS)
def test_an_int_shape_never_floats_a_bound(value):
    """Only a float shape normalizes; an int bound is already the number it is."""
    node = _shape_node(Int(min=Min(value), max=Max(value + 10**40)),
                       _Document(), labelled=False)
    assert type(node["min"]) is int and node["min"] == value


# ---------------------------------------------------------------------------
# The emitter reads the schema and the value, and nothing else
# ---------------------------------------------------------------------------

def _written_file(directory, name="probe.txt", body="hi"):
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def test_the_router_is_handed_the_shape_the_author_wrote():
    """Nothing is stripped out of a slot before it is routed, and nothing needs to be.

    The emitter used to filter the file atom out of a `Str` before asking the
    router which option a default inhabits, because the atom went to the disk and
    the disk would then have picked the option. `FileHint` now answers from the
    text of the value, so the router is handed the shapes themselves and the
    extension is free to tell two options apart like any other limit — it is
    spelled in the value, and the value travels with the schema.
    """
    def type_of_default(name: str) -> str:
        @dataclass
        class _Union:
            x: (list[Annotated[str, FileHint(extensions=(".txt",))] | int]
                | list[Annotated[str, FileHint(extensions=(".md",))] | bool]
                ) = field(default_factory=lambda: [name])

        document = struct_of(_Union).to_dict()
        return document["defs"]["structs"]["_Union"]["fields"][0]["default"]["$type"]

    # Neither file exists, and neither answer needs one: the suffix is all either
    # option ever looks at.
    assert type_of_default("notes.txt") == "list[str | int]"
    assert type_of_default("notes.md") == "list[str | bool]"


def test_every_limit_of_a_string_still_tells_two_options_apart():
    """Nothing was traded away to make the atom safe: the whole shape routes.

    The emitter used to route a *copy* of the `Str` with the file atom taken out,
    and the copy had to be rebuilt with care — a `Str` that lost its compiled
    pattern on the way through would have quietly stopped matching. There is no
    copy any more, so the shape the router reads is the shape the author wrote,
    atom and all, and every limit on it still has a vote.
    """
    rich = Str(min=Min(1), max=Max(300),
               pattern=Pattern(r".+\.txt", message="needs .txt"),
               file_hint=FileHint(extensions=(".txt",), min_size=1, max_size=99),
               rows=Rows(3), placeholder=Placeholder("pick one"),
               _extras=(("pkg.a", "1"), ("pkg.b", "2")))
    short = Str(max=Max(4))

    assert rich._compiled is not None
    assert value_branch((rich, short), "a.txt") is rich
    # The pattern turns this one away, the length turns the next one away, and a
    # value no option takes is reported rather than assigned.
    assert value_branch((rich, short), "abcd") is short
    assert value_branch((rich, short), "a.md") is short
    assert value_branch((rich, short), "a.markdown") is None


def test_the_document_publishes_the_file_hint_with_every_narrowing():
    """The atom travels whole, at every depth: the boundary is where sizes are used."""
    @dataclass
    class _Marked:
        a: Annotated[str, FileHint(extensions=(".txt", ".md"), min_size=1,
                                   max_size=10)]
        b: Annotated[str, FileHint()]
        c: list[Annotated[str, FileHint(min_size=5)]]
        d: list[list[Annotated[str, FileHint(max_size=7)]]]

    fields = struct_of(_Marked).to_dict()["defs"]["structs"]["_Marked"]["fields"]
    assert fields[0]["shape"][0]["file_hint"] == {
        "extensions": [".txt", ".md"], "min_size": 1, "max_size": 10}
    assert fields[1]["shape"][0]["file_hint"] == {}
    assert fields[2]["shape"][0]["item"][0]["file_hint"] == {"min_size": 5}
    assert (fields[3]["shape"][0]["item"][0]["item"][0]["file_hint"]
            == {"max_size": 7})


def test_the_option_a_string_default_inhabits_ignores_the_file(tmp_path):
    """An atom with nothing to say does not tell two options apart, and disk never does."""
    path = _written_file(tmp_path)

    @dataclass
    class _Union:
        x: (list[Annotated[str, FileHint()] | int]
            | list[str | bool]) = field(default_factory=lambda: [str(path)])

    schema = struct_of(_Union)
    with_file = json.dumps(schema.to_dict())
    os.remove(path)
    without_file = json.dumps(schema.to_dict())

    assert with_file == without_file
    default = json.loads(with_file)["defs"]["structs"]["_Union"]["fields"][0]["default"]
    # The first option, chosen on the limits alone, exactly as declared.
    assert default["$type"] == "list[str | int]"


def test_a_one_option_slot_and_a_two_option_slot_choose_alike():
    """The shortcut for a single option must not be a second rule."""
    # A path that was never on disk. Writing one used to be the only way to get
    # the two-option schema past `to_dict()`; now neither slot has any way to ask.
    absent = os.path.join("no", "such", "place", "probe.txt")

    one = struct_of(make_dataclass(
        "_S", [("x", Annotated[str, FileHint()], field(default=absent))]))
    two = struct_of(make_dataclass(
        "_S", [("x", Annotated[str, FileHint()] | int, field(default=absent))]))

    def default_of(schema):
        return schema.to_dict()["defs"]["structs"]["_S"]["fields"][0]["default"]

    assert default_of(one) == absent
    assert default_of(two) == absent


_ACROSS_PROCESSES = """
import json, os, sys
from dataclasses import dataclass, field
from typing import Annotated
from pytypehint import FileHint, struct_of

path = sys.argv[1]

@dataclass
class Subject:
    x: (list[Annotated[str, FileHint()] | int]
        | list[str | bool]) = field(default_factory=lambda: [path])

schema = struct_of(Subject)
if sys.argv[2] == "delete":
    os.remove(path)
print(json.dumps(schema.to_dict()))
"""


def _document_from(path, action, seed, cwd):
    environment = {**os.environ, "PYTHONHASHSEED": seed}
    result = subprocess.run(
        [sys.executable, "-c", _ACROSS_PROCESSES, str(path), action],
        capture_output=True, text=True, env=environment, cwd=str(cwd))
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_two_processes_write_the_same_document_whatever_the_disk_says(tmp_path):
    """'Nothing outside the process is consulted either.' — docs/contract.md"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    path = _written_file(tmp_path)
    keeping = _document_from(path, "keep", "0", root)
    path = _written_file(tmp_path)
    deleting = _document_from(path, "delete", "12345", root)
    path = _written_file(tmp_path)
    # A relative path resolves against the working directory, so a document that
    # never asks the filesystem cannot notice the change of directory either.
    other_cwd = _document_from(path, "keep", "7", elsewhere)

    assert keeping == deleting
    assert keeping == other_cwd


def test_every_published_default_round_trips_through_decode_and_build():
    """A default taken from the document is valid input to the pipeline."""
    @dataclass
    class _Nested:
        y: float = 9007199254740992.0

    @dataclass
    class _Subject:
        # A name, not a file: the round trip never touches whatever is on disk.
        marked: Annotated[str, FileHint()] = "probe.txt"
        whole: float = 2.0**200
        wide: int = 2**53 + 1
        pair: float | int = 2.0**60
        items: list[float] = field(default_factory=lambda: [2.0**53, 1.5])
        inner: _Nested = field(default_factory=_Nested)

    schema = struct_of(_Subject)
    document = json.loads(json.dumps(schema.to_dict()))
    defaults = {f["name"]: f["default"]
                for f in document["defs"]["structs"]["_Subject"]["fields"]}
    built = schema.build(schema.decode(defaults))
    original = schema.build({})

    assert built == original
    for name in defaults:
        assert type(getattr(built, name)) is type(getattr(original, name))


# ---------------------------------------------------------------------------
# A path in a nested dataclass, which is where the world used to get in
# ---------------------------------------------------------------------------
#
# These four were failing for as long as the file atom went to the
# disk. The emitter defended itself by stripping the atom out of a `Str` before
# routing a default, and that filter descended into `List.item` but stopped at
# `Struct` — so a path one dataclass deep still reached the filesystem, and
# `to_dict()` either failed on a schema `struct_of()` had accepted or quietly let
# the disk choose a `$type`. The atom answers from the text now, there is no
# filter left to have a hole in it, and each of these states the observable
# property directly: the document is a function of the schema and the value.

@dataclass
class _Holds:
    p: Annotated[str, FileHint()]


@dataclass
class _Plain:
    q: int = 0


@dataclass
class _HoldsTxt:
    p: Annotated[str, FileHint(extensions=(".txt",), min_size=1, max_size=64)]


def test_a_path_inside_a_nested_dataclass_does_not_reach_the_filesystem(tmp_path):
    """Deleting the file under a nested default does not move a byte of the document."""
    path = _written_file(tmp_path)

    @dataclass
    class _Subject:
        x: list[_Holds] | list[_Plain] = field(
            default_factory=lambda: [_Holds(p=str(path))])

    schema = struct_of(_Subject)
    before = json.dumps(schema.to_dict())
    os.remove(path)
    assert json.dumps(schema.to_dict()) == before


def test_the_gap_does_not_widen_with_depth(tmp_path):
    """The same subject one level deeper: `list[list[Struct]]` answers alike."""
    path = _written_file(tmp_path)

    @dataclass
    class _Subject:
        x: list[list[_Holds]] | list[list[_Plain]] = field(
            default_factory=lambda: [[_Holds(p=str(path))]])

    schema = struct_of(_Subject)
    before = json.dumps(schema.to_dict())
    os.remove(path)
    assert json.dumps(schema.to_dict()) == before


def test_the_document_does_not_depend_on_the_working_directory(tmp_path, monkeypatch):
    """A relative path is the spelling whose meaning would move with the cwd.

    `rel.txt` names one file from `home` and another — or none — from `away`.
    Nothing resolves it, so the document cannot tell the two directories apart.
    """
    home = tmp_path / "home"
    away = tmp_path / "away"
    home.mkdir()
    away.mkdir()
    _written_file(home, "rel.txt")

    monkeypatch.chdir(home)

    @dataclass
    class _Subject:
        x: list[_Holds] | list[_Plain] = field(
            default_factory=lambda: [_Holds(p="rel.txt")])

    schema = struct_of(_Subject)
    at_home = json.dumps(schema.to_dict())
    monkeypatch.chdir(away)
    assert json.dumps(schema.to_dict()) == at_home


def test_the_filesystem_never_picks_the_discriminator_of_a_default(tmp_path):
    """Two options that differ only by the atom: the disk gets no vote on `$type`.

    This is the failure with no error attached — the document would simply have
    named a different option before and after the file was deleted, and nothing
    would have warned the reader that the two were ever supposed to be one.
    """
    path = _written_file(tmp_path)

    marked = Struct(cls=_Holds, fields=(
        Field(name="p", shape=(Str(file_hint=FileHint()),)),))
    bare = Struct(cls=_Holds, fields=(Field(name="p", shape=(Str(),)),))
    subject = Struct(cls=_Plain, fields=(
        Field(name="q", shape=(List(item=(marked, Int())),
                               List(item=(bare, Bool()))),
              default=[_Holds(p=str(path))]),))

    before = json.dumps(subject.to_dict())
    os.remove(path)
    assert json.dumps(subject.to_dict()) == before


def test_one_schema_writes_one_document_wherever_the_file_is_and_wherever_we_stand(
        tmp_path, monkeypatch):
    """The property the whole change exists for, pressed from every side at once.

    One schema, one default under `FileHint`, and every arrangement of the world
    that could plausibly reach it: the file present, the file deleted, a different
    file put back behind the same relative name, and the process standing in three
    different directories while all of that happens. The document is compared as
    bytes, not as a `dict`, because two documents that differ only in the `$type`
    of a default still compare equal key by key if a reader is careless about
    which option it looks under.

    The cross-process axis is next door in
    `test_two_processes_write_the_same_document_whatever_the_disk_says`; this one
    holds the schema object fixed instead, so a document that changed would prove
    `to_dict()` itself read something it had no business reading.
    """
    here = tmp_path / "here"
    there = tmp_path / "there"
    here.mkdir()
    there.mkdir()
    absolute = _written_file(here, "kept.txt")
    _written_file(here, "rel.txt")

    @dataclass
    class _Subject:
        # A relative name, an absolute one, and a path one dataclass deep under a
        # slot with two options — the arrangement that used to reach the disk.
        loose: Annotated[str, FileHint(extensions=(".txt",))] = "rel.txt"
        nested: list[_HoldsTxt] | list[_Plain] = field(
            default_factory=lambda: [_HoldsTxt(p=str(absolute))])
        listed: (list[Annotated[str, FileHint()] | int]
                 | list[str | bool]) = field(default_factory=lambda: ["rel.txt"])

    monkeypatch.chdir(here)
    schema = struct_of(_Subject)
    written = {"the file is there, and so are we": json.dumps(schema.to_dict())}

    os.remove(absolute)
    os.remove(here / "rel.txt")
    written["both files deleted"] = json.dumps(schema.to_dict())

    monkeypatch.chdir(there)
    written["deleted, and standing elsewhere"] = json.dumps(schema.to_dict())

    # The same relative name now points at a different file: a document that
    # resolved it would follow the move, one that reads the text cannot.
    _written_file(there, "rel.txt", body="a different body entirely")
    written["another file behind the same name"] = json.dumps(schema.to_dict())

    monkeypatch.chdir(tmp_path)
    _written_file(here, "kept.txt")
    written["restored, from a third directory"] = json.dumps(schema.to_dict())

    first = written["the file is there, and so are we"]
    for scenario, document in written.items():
        assert document == first, scenario

    # And the bytes say what they should: the default landed in the option the
    # limits name, not in whichever one the disk happened to agree with.
    fields = json.loads(first)["defs"]["structs"]["_Subject"]["fields"]
    assert {f["name"]: f["default"] for f in fields}["loose"] == "rel.txt"


# ---------------------------------------------------------------------------
# Defects
# ---------------------------------------------------------------------------

def test_two_bounds_that_are_one_atom_publish_one_number():
    # Built through `Struct` rather than `Annotated`, and compared as bytes: the
    # typing cache hands `Annotated[float, Min(0)]` and `Annotated[float, Min(-0.0)]`
    # back as one object, and `-0.0 == 0.0` hides the difference from a `dict`
    # comparison. Either shortcut makes this pass without the fix.
    assert Min(-0.0) == Min(0) and hash(Min(-0.0)) == hash(Min(0))
    # All three spellings of the one atom, compared as one set: two of them
    # agreeing pairwise would not stop the third from writing its own document.
    assert len({_float_bytes(min=Min(-0.0)), _float_bytes(min=Min(0)),
                _float_bytes(min=Min(0.0))}) == 1
    assert _float_bytes(max=Max(-0.0)) == _float_bytes(max=Max(0.0))
    assert (Choices(values=(-0.0,)) == Choices(values=(0.0,))
            and _float_bytes(choices=Choices(values=(-0.0,)))
            == _float_bytes(choices=Choices(values=(0.0,))))


def test_a_negative_zero_default_still_keeps_its_sign():
    """The companion fact, and the reason the fix above belongs to bounds only:
    a default is a value the author wrote, not an atom two spellings share."""
    written = struct_of(make_dataclass(
        "_Z", [("x", float, field(default=-0.0))])).to_dict()
    default = written["defs"]["structs"]["_Z"]["fields"][0]["default"]
    assert math.copysign(1.0, default) == -1.0
    assert Extra("pkg.k", "v").key == "pkg.k"

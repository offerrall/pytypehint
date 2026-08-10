"""Generative properties of the portable form: `to_dict`, `decode`, and the wire between them.

The example tests pin what one schema writes and reads. These pin what must hold
across *every* schema the closed vocabulary can spell, so a change that keeps the
examples green while bending the shape of the format still has something to fail
against.

Two generators feed the file, in that order:

* a plain `random.Random` on fixed seeds, which composes hints out of the
  vocabulary, samples values from the *compiled* shapes and drives the large
  batteries — there the point is volume;
* Hypothesis over curated pools, for the finer equivalences — there the point is
  which case fires.

Nothing here asserts a timing, and every seed is fixed, so the suite is
reproducible run to run.
"""

import json
import random
from copy import deepcopy
from dataclasses import dataclass, field, is_dataclass, make_dataclass
from datetime import date, time, timedelta
from enum import Enum
from functools import reduce
from operator import or_
from typing import Annotated, get_args

import pytest
from hypothesis import given, settings, strategies as st

from pytypehint import (
    Choices, Description, Extra, IsPassword, Label, Max, Min, MultipleOf,
    OptionalToggle, Pattern, Placeholder, Rows, SchemaTypeError,
    SchemaValueError, Slider, Step, Struct, signature_of, struct_of,
)
from pytypehint.shapes import (
    Bool, Date, EnumShape, Float, Int, List, NoneShape, Str, Time,
)
from pytypehint.utils import MISSING

_PORTABLE_TYPES = (dict, list, str, int, float, bool, type(None))
_TYPE = "$type"
_VALUE = "$value"


# ------------------------------------ The fixed pool the generator draws from

class _Role(Enum):
    ADMIN = "admin"
    USER = "user"


class _Status(Enum):
    OPEN = 1
    CLOSED = 2
    HELD = 3


class _Cross(Enum):
    # docs/decode.md, 'Enums travel by member name': names and values crossed, so
    # a decoder that read values instead of names would be silently wrong here.
    RED = "BLUE"
    BLUE = "RED"


_ENUM_POOL = (_Role, _Status, _Cross)


@dataclass
class _Node:
    """Recursive through a list: the empty list is the base case."""
    tag: str
    children: list["_Node"]


@dataclass
class _Link:
    """Recursive through an optional: None is the base case."""
    label: str
    nxt: "_Link | None" = None


_RECURSIVE_POOL = (_Node, _Link)

_LETTERS = "abcdefghijklmnopqrstuvwxyz"
_DATE_FLOOR = date(2000, 1, 1)


# ------------ A deterministic schema generator (stdlib random, no Hypothesis)

def _name(rng) -> str:
    return f"S{rng.getrandbits(30)}"


def _extra(rng):
    return (Extra("tests.origin", "generated"),) if rng.random() < 0.15 else ()


def _int_hint(rng):
    roll = rng.random()
    if roll < 0.22:
        low = rng.randrange(0, 10)
        high = low + rng.randrange(1, 40)
        atoms = [Min(low), Max(high)]
        if rng.random() < 0.3:
            atoms.append(Slider(show_value=rng.random() < 0.5))
        if rng.random() < 0.3:
            atoms.append(Step(rng.randrange(1, 4)))
        return Annotated[tuple([int, *atoms, *_extra(rng)])]
    if roll < 0.36:
        return Annotated[tuple([int, Choices(values=(1, 4, 9)), *_extra(rng)])]
    if roll < 0.46:
        return Annotated[int, Min(0), Max(100), MultipleOf(5)]
    if roll < 0.56:
        return Annotated[int, Min(0, exclusive=True), Max(50, exclusive=True)]
    return int


def _float_hint(rng):
    roll = rng.random()
    if roll < 0.25:
        return Annotated[tuple([float, Min(0.0), Max(10.0), *_extra(rng)])]
    if roll < 0.40:
        return Annotated[float, Min(0.0, exclusive=True), Max(10.0),
                         Slider(show_value=False), Step(0.5)]
    if roll < 0.50:
        return Annotated[float, Choices(values=(0.5, 2.5))]
    return float


def _str_hint(rng):
    roll = rng.random()
    if roll < 0.20:
        return Annotated[tuple([str, Min(1), Max(8), *_extra(rng)])]
    # The only pattern the generator emits, so the value sampler can always
    # satisfy it: lowercase letters, at least one.
    if roll < 0.34:
        return Annotated[str, Pattern(r"[a-z]+", message="lowercase letters only")]
    if roll < 0.44:
        return Annotated[str, Choices(values=("alpha", "beta"))]
    if roll < 0.56:
        return Annotated[str, Placeholder("type here"), Rows(3), IsPassword()]
    return str


def _bool_hint(rng):
    # Bool admits no limits at all, so `Extra` is the only atom it can carry.
    return Annotated[bool, Extra("tests.origin", "generated")] if rng.random() < 0.2 else bool


def _date_hint(rng):
    roll = rng.random()
    if roll < 0.25:
        return Annotated[date, Min(date(2020, 1, 1)), Max(date(2030, 12, 31))]
    if roll < 0.35:
        return Annotated[date, Choices(values=(date(2024, 6, 1), date(2024, 6, 2)))]
    if roll < 0.45:
        return Annotated[tuple([date, Min(date(2020, 1, 1), exclusive=True),
                                Placeholder("YYYY-MM-DD"), *_extra(rng)])]
    return date


def _time_hint(rng):
    roll = rng.random()
    if roll < 0.25:
        return Annotated[time, Min(time(9, 0)), Max(time(18, 0))]
    if roll < 0.35:
        return Annotated[time, Choices(values=(time(9, 0), time(17, 30)))]
    if roll < 0.45:
        return Annotated[tuple([time, Max(time(23, 0)), *_extra(rng)])]
    return time


_PRIMITIVE_HINTS = {
    "int": _int_hint, "float": _float_hint, "str": _str_hint,
    "bool": _bool_hint, "date": _date_hint, "time": _time_hint,
}

# Tags a union slot may hold. Two options of the same tag would collide on
# option identity (docs/restrictions.md, 'Duplicate option types in a union'),
# so a tag is drawn at most once and the twins below are drawn apart.
_TAGS = ("int", "float", "str", "bool", "date", "time", "enum", "list", "struct")

# Pairs whose portable spellings collide on purpose (docs/contract.md, 'Reading
# the wire from the document'): every one of them forces a named option.
_COLLIDING_PAIRS = (
    ("int", "float"), ("str", "date"), ("str", "time"), ("date", "time"),
    ("str", "enum"), ("enum", "enum"), ("list", "list"), ("struct", "struct"),
    ("date", "enum"),
)


def _list_hint(rng, depth, item=None):
    if item is None:
        item = _random_schema(rng, depth - 1)
    atoms = []
    if rng.random() < 0.3:
        # Only ever a zero floor, so an exhausted depth can always answer [].
        atoms += [Min(0), Max(3)]
    atoms += list(_extra(rng))
    return Annotated[tuple([list[item], *atoms])] if atoms else list[item]


def _struct_hint(rng, depth, used):
    if depth > 0 and rng.random() < 0.55:
        return _random_dataclass(rng, depth - 1, defaults="none")
    pool = [cls for cls in _RECURSIVE_POOL if cls not in used]
    if not pool:
        return _random_dataclass(rng, 0, defaults="none")
    return rng.choice(pool)


def _options_for_tags(rng, tags, depth):
    """One hint per tag, drawing twins apart so no two options share an identity."""
    enums = list(_ENUM_POOL)
    rng.shuffle(enums)
    item_kinds = ["str", "int", "float", "bool", "date"]
    rng.shuffle(item_kinds)
    used_structs = []

    options = []
    for tag in tags:
        if tag in _PRIMITIVE_HINTS:
            options.append(_PRIMITIVE_HINTS[tag](rng))
        elif tag == "enum":
            options.append(enums.pop())
        elif tag == "list":
            twins = tags.count("list")
            # Two lists in one slot must spell different items, or their
            # option ids coincide: list[int] and list[Annotated[int, Min(0)]]
            # are one identity, not two.
            item = _PRIMITIVE_HINTS[item_kinds.pop()](rng) if twins > 1 else None
            options.append(_list_hint(rng, depth, item))
        elif tag == "struct":
            cls = _struct_hint(rng, depth, used_structs)
            used_structs.append(cls)
            options.append(cls)
    return options


def _random_schema(rng, depth):
    """A hint from the closed vocabulary, at most `depth` containers deep."""
    if depth <= 0:
        tags = [rng.choice(("int", "float", "str", "bool", "date", "time", "enum"))]
    else:
        roll = rng.random()
        if roll < 0.42:
            tags = [rng.choice(_TAGS)]
        elif roll < 0.72:
            tags = list(rng.choice(_COLLIDING_PAIRS))
        else:
            tags = rng.sample(_TAGS, rng.randint(2, 3))

    options = _options_for_tags(rng, tags, depth)
    hint = reduce(or_, options)
    if rng.random() < 0.3:
        # None goes last: `X | None` is how the vocabulary spells optionality.
        hint = hint | None
    return hint


def _is_optional(hint) -> bool:
    return type(None) in get_args(hint)


def _field_hint(rng, depth):
    """A schema plus the field notation only a field may carry."""
    hint = _random_schema(rng, depth)
    atoms = []
    if rng.random() < 0.3:
        atoms.append(Label("A label"))
    if rng.random() < 0.2:
        atoms.append(Description("What the field means."))
    if _is_optional(hint) and rng.random() < 0.3:
        atoms.append(OptionalToggle(rng.random() < 0.5))
    return Annotated[tuple([hint, *atoms])] if atoms else hint


def _compiled_shape(hint):
    """The compiled option tuple of `hint`, for sampling a value that fits it."""
    return struct_of(make_dataclass("_Probe", [("x", hint)])).fields[0].shape


def _default_spec(value):
    # A list or an instance is a mutable default: dataclasses refuses it inline,
    # and a recipe is what defaults.md asks for anyway. deepcopy keeps the
    # servings independent, which is the purity the core does not police.
    if type(value) is list or (is_dataclass(value) and not isinstance(value, type)):
        return field(default_factory=lambda v=value: deepcopy(v))
    return field(default=value)


def _random_dataclass(rng, depth, defaults="none"):
    count = rng.randint(1, 3)
    hints = [(f"f{i}", _field_hint(rng, depth)) for i in range(count)]

    # Fields without a default must come first; that is dataclass syntax, not
    # anything the core decides.
    without = 0 if defaults == "all" else count if defaults == "none" else rng.randint(0, count)

    spec = []
    for i, (name, hint) in enumerate(hints):
        if i < without:
            spec.append((name, hint))
        else:
            value = _sample_options(_compiled_shape(hint), rng, 2)
            spec.append((name, hint, _default_spec(value)))
    return make_dataclass(_name(rng), spec)


def _random_function(rng, depth, defaults="none"):
    count = rng.randint(1, 3)
    params = [(f"p{i}", _field_hint(rng, depth)) for i in range(count)]
    without = 0 if defaults == "all" else count if defaults == "none" else rng.randint(0, count)

    namespace = {}
    written = []
    for i, (name, hint) in enumerate(params):
        if i < without:
            written.append(name)
        else:
            namespace[f"_d{i}"] = _sample_options(_compiled_shape(hint), rng, 2)
            written.append(f"{name}=_d{i}")

    exec(f"def _generated({', '.join(written)}): pass", namespace)
    fn = namespace["_generated"]
    fn.__annotations__ = {name: hint for name, hint in params}
    fn.__doc__ = "A generated function."
    return fn


# --------------------- Sampling an exact Python value out of a compiled shape

def _seconds(t) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second


def _rank(shape) -> int:
    """How much recursion an option can still demand. Lowest wins at depth 0."""
    kind = type(shape)
    if kind is NoneShape:
        return 0
    if kind in (List, Struct):
        return 2
    return 1


def _sample_options(shapes, rng, depth):
    if depth > 0:
        shape = rng.choice(shapes)
    else:
        shape = sorted(shapes, key=_rank)[0]
    return _sample_shape(shape, rng, depth)


def _sample_shape(shape, rng, depth):
    kind = type(shape)

    if kind is NoneShape:
        return None
    if kind is Bool:
        return rng.random() < 0.5
    if kind is EnumShape:
        return rng.choice(list(shape.cls))

    if kind is Int:
        if shape.choices is not None:
            return rng.choice(shape.choices.values)
        low = 0 if shape.min is None else shape.min.value + shape.min.exclusive
        high = low + 40 if shape.max is None else shape.max.value - shape.max.exclusive
        high = max(low, high)
        if shape.multiple_of is not None:
            step = shape.multiple_of.value
            first = -(-low // step) * step
            last = (high // step) * step
            return first if last < first else rng.randrange(first, last + 1, step)
        return rng.randint(low, high)

    if kind is Float:
        if shape.choices is not None:
            return rng.choice(shape.choices.values)
        low = 0.0 if shape.min is None else float(shape.min.value)
        high = low + 10.0 if shape.max is None else float(shape.max.value)
        # A strict interior point satisfies an exclusive bound on either side.
        return float(low + (high - low) * rng.choice((0.25, 0.5, 0.75)))

    if kind is Str:
        if shape.choices is not None:
            return rng.choice(shape.choices.values)
        low = 0 if shape.min is None else shape.min.value
        if shape.pattern is not None:
            low = max(low, 1)
        high = low + 6 if shape.max is None else max(low, shape.max.value)
        return "".join(rng.choice(_LETTERS) for _ in range(rng.randint(low, high)))

    if kind is Date:
        if shape.choices is not None:
            return rng.choice(shape.choices.values)
        low = _DATE_FLOOR if shape.min is None else (
            shape.min.value + timedelta(days=1) if shape.min.exclusive else shape.min.value)
        high = low + timedelta(days=3650) if shape.max is None else (
            shape.max.value - timedelta(days=1) if shape.max.exclusive else shape.max.value)
        high = max(low, high)
        return date.fromordinal(rng.randint(low.toordinal(), high.toordinal()))

    if kind is Time:
        if shape.choices is not None:
            return rng.choice(shape.choices.values)
        low = 0 if shape.min is None else _seconds(shape.min.value) + shape.min.exclusive
        high = 86399 if shape.max is None else _seconds(shape.max.value) - shape.max.exclusive
        high = max(low, high)
        drawn = rng.randint(low, high)
        return time(drawn // 3600, drawn // 60 % 60, drawn % 60)

    if kind is List:
        low = 0 if shape.min is None else shape.min.value
        high = 3 if shape.max is None else min(3, shape.max.value)
        count = low if depth <= 0 else rng.randint(low, max(low, high))
        return [_sample_options(shape.item, rng, depth - 1) for _ in range(count)]

    if kind is Struct:
        return shape.cls(**{f.name: _sample_options(f.shape, rng, depth - 1)
                            for f in shape.fields})

    raise AssertionError(f"no sampler for {kind.__name__}")


# -------- A test encoder: exact Python out, portable in, per docs/contract.md

def _wire_kinds(shape):
    """The portable types an option can arrive as (docs/decode.md, 'The portable tree')."""
    kind = type(shape)
    if kind is Float:
        return (float, int)
    if kind in (Date, Time, EnumShape):
        return (str,)
    if kind is Struct:
        return (dict,)
    return (shape.pytype,)


def _colliding(shapes):
    """Options that share a portable spelling, so a bare value cannot name one."""
    plain = [s for s in shapes if type(s) is not Struct]
    counts: dict[type, int] = {}
    for shape in plain:
        for kind in _wire_kinds(shape):
            counts[kind] = counts.get(kind, 0) + 1
    return [s for s in plain if any(counts[k] > 1 for k in _wire_kinds(s))]


def _shares_runtime_type(shapes, shape) -> bool:
    """Two options a decoded value could still not be told apart by."""
    if type(shape) is Struct:
        return False
    return sum(1 for s in shapes
               if type(s) is not Struct and s.pytype is shape.pytype) > 1


def _fits(shape, value) -> bool:
    if type(value) is not shape.pytype:
        return False
    if type(shape) is List:
        return all(any(_fits(option, item) for option in shape.item) for item in value)
    return True


def _pick(shapes, value):
    for shape in shapes:
        if _fits(shape, value):
            return shape
    raise AssertionError(f"{value!r} fits no option of {shapes!r}")


def _encode(shapes, value):
    """Write one exact Python value as the wire, naming the option where needed."""
    shape = _pick(shapes, value)
    written = _encode_shape(shape, value)
    if type(shape) is Struct:
        if sum(1 for s in shapes if type(s) is Struct) > 1:
            return {_TYPE: shape.cls.__name__, **written}
        return written
    if any(s is shape for s in _colliding(shapes)):
        return {_TYPE: shape.option_id(), _VALUE: written}
    return written


def _encode_shape(shape, value):
    kind = type(shape)
    if kind is Date:
        return value.isoformat()
    if kind is Time:
        return value.isoformat(timespec="seconds")
    if kind is EnumShape:
        return value.name
    if kind is List:
        return [_encode(shape.item, item) for item in value]
    if kind is Struct:
        return {f.name: _encode(f.shape, getattr(value, f.name)) for f in shape.fields}
    if kind is Float:
        return float(value)
    return value


def _exact(shapes, value):
    """The same value as the *exact* tree `build` takes: dataclasses as dicts."""
    shape = _pick(shapes, value)
    written = _exact_shape(shape, value)
    if type(shape) is Struct:
        if sum(1 for s in shapes if type(s) is Struct) > 1:
            return {_TYPE: shape.cls.__name__, **written}
        return written
    if _shares_runtime_type(shapes, shape):
        return {_TYPE: shape.option_id(), _VALUE: written}
    return written


def _exact_shape(shape, value):
    kind = type(shape)
    if kind is List:
        return [_exact(shape.item, item) for item in value]
    if kind is Struct:
        return {f.name: _exact(f.shape, getattr(value, f.name)) for f in shape.fields}
    return value


# --------------------------------------------------------- Inspection helpers

def _containers(tree, found=None):
    """id() of every dict and list in a tree. The tree must stay alive."""
    if found is None:
        found = set()
    if type(tree) is dict:
        found.add(id(tree))
        for value in tree.values():
            _containers(value, found)
    elif type(tree) is list:
        found.add(id(tree))
        for value in tree:
            _containers(value, found)
    return found


def _leaks(tree, path=()):
    """Every value that is not one a JSON document can carry."""
    if type(tree) not in _PORTABLE_TYPES:
        return [(path, type(tree).__name__)]
    found = []
    if type(tree) is dict:
        for key, value in tree.items():
            if type(key) is not str:
                found.append((path, f"key of type {type(key).__name__}"))
            found.extend(_leaks(value, (*path, key)))
    elif type(tree) is list:
        for index, value in enumerate(tree):
            found.extend(_leaks(value, (*path, index)))
    return found


def _decode_recovers(shapes, value) -> bool:
    """Whether `decode` can hand this exact value back, at every depth it reaches.

    Two documented cases where it cannot, and both are right: a dataclass stays a
    dict until `build` constructs it (docs/build.md, 'Data in, objects out'), and
    a wrapper survives decode wherever the options it separates 'also share a
    Python runtime type' (docs/decode.md, 'Unions'). Both are checked through
    `build` instead.
    """
    shape = _pick(shapes, value)
    if type(shape) is Struct or _shares_runtime_type(shapes, shape):
        return False
    if type(shape) is List:
        return all(_decode_recovers(shape.item, item) for item in value)
    return True


def _census(struct, seen=None, visited=None):
    """Which constructs a compiled schema actually contains."""
    if seen is None:
        seen, visited = set(), set()
    if id(struct) in visited:
        return seen
    visited.add(id(struct))
    for f in struct.fields:
        if len(f.shape) > 1:
            seen.add("union")
        if f.default is not MISSING:
            seen.add("default")
        if f.label is not None or f.description is not None:
            seen.add("notation")
        _census_shapes(f.shape, seen, visited)
    return seen


def _census_shapes(shapes, seen, visited):
    for shape in shapes:
        seen.add(type(shape).__name__)
        if type(shape) is List:
            if len(shape.item) > 1:
                seen.add("union")
            _census_shapes(shape.item, seen, visited)
        elif type(shape) is Struct:
            _census(shape, seen, visited)


# ---------------------------------- The corpora, compiled once on fixed seeds

@dataclass(frozen=True)
class _Corpus:
    schemas: tuple
    skipped: tuple
    attempted: int

    @property
    def skip_rate(self) -> float:
        return len(self.skipped) / self.attempted


def _corpus(seed, count, defaults, depth=2, signatures=False):
    rng = random.Random(seed)
    made, skipped = [], []
    for _ in range(count):
        try:
            if signatures:
                made.append(signature_of(_random_function(rng, depth, defaults)))
            else:
                made.append(struct_of(_random_dataclass(rng, depth, defaults)))
        except (TypeError, ValueError) as error:
            skipped.append(f"{type(error).__name__}: {error}")
    return _Corpus(schemas=tuple(made), skipped=tuple(skipped), attempted=count)


_PLAIN = _corpus(seed=20260808, count=220, defaults="none")
_DEFAULTED = _corpus(seed=613, count=180, defaults="all")
_MIXED = _corpus(seed=99991, count=100, defaults="some")
_SIGNATURES = _corpus(seed=4242, count=90, defaults="some", signatures=True)
_ALL = _PLAIN.schemas + _DEFAULTED.schemas + _MIXED.schemas + _SIGNATURES.schemas


# ------------------------------------------------------- the generator itself


def test_the_generator_skips_almost_nothing_so_the_batteries_are_not_no_ops():
    """A generator that quietly discarded its output would make every battery below vacuous."""
    for name, corpus in (("plain", _PLAIN), ("defaulted", _DEFAULTED),
                         ("mixed", _MIXED), ("signatures", _SIGNATURES)):
        assert corpus.skip_rate < 0.02, \
            f"{name}: {corpus.skip_rate:.1%} skipped, first reasons {corpus.skipped[:5]}"
        assert len(corpus.schemas) > corpus.attempted * 0.95


def test_the_corpus_reaches_every_construct_the_properties_claim_to_cover():
    """Unions, optionals, lists, enums, dates, times and nested dataclasses must all occur."""
    seen = set()
    for schema in _PLAIN.schemas:
        _census(schema, seen, set())

    assert {"union", "notation", "Int", "Float", "Str", "Bool", "Date", "Time",
            "NoneShape", "List", "EnumShape", "Struct"} <= seen

    defaulted = set()
    for schema in _DEFAULTED.schemas:
        _census(schema, defaulted, set())
    assert "default" in defaulted


# ----------- 1, 10 — the document is a JSON document and carries nothing else

def test_every_generated_document_survives_json_dumps_and_loads_unchanged():
    """docs/contract.md: to_dict writes 'dicts, lists, strings, numbers, booleans and null, and nothing else'."""
    for schema in _ALL:
        document = schema.to_dict()
        text = json.dumps(document)
        assert json.loads(text) == document


def test_no_value_in_a_generated_document_escapes_the_portable_types():
    """docs/contract.md: 'the contract as data' — a date, an enum member or a Shape reaching the tree is a leak."""
    for schema in _ALL:
        leaks = _leaks(schema.to_dict())
        assert leaks == [], f"{schema!r}: {leaks[:3]}"


def test_every_document_carries_the_skeleton_the_format_promises():
    """docs/contract.md, 'Documents': "`defs` is always present with both tables, even empty"."""
    for schema in _ALL:
        document = schema.to_dict()
        assert document["v"] == 1
        assert set(document["defs"]) == {"structs", "enums"}
        if document["kind"] == "struct":
            assert document["root"] in document["defs"]["structs"]
        else:
            assert document["kind"] == "signature"
            assert isinstance(document["params"], list)


def _slots(document):
    """Every shape array in a document: a field's options, and a list's item options."""
    pending = [f["shape"] for definition in document["defs"]["structs"].values()
               for f in definition["fields"]]
    if document["kind"] == "signature":
        pending += [p["shape"] for p in document["params"]]

    slots = []
    while pending:
        slot = pending.pop()
        slots.append(slot)
        for node in slot:
            if node["type"] == "list":
                pending.append(node["item"])
    return slots


def test_every_ref_in_a_document_resolves_inside_that_same_document():
    """docs/contract.md, 'Definitions': 'Always a reference, never inlined' — so every pointer must land."""
    for schema in _ALL:
        document = schema.to_dict()
        structs, enums = document["defs"]["structs"], document["defs"]["enums"]
        for slot in _slots(document):
            for node in slot:
                if node["type"] == "struct":
                    assert node["ref"] in structs
                elif node["type"] == "enum":
                    assert node["ref"] in enums
        for identifier, definition in structs.items():
            assert type(definition["name"]) is str
            assert identifier.split("#")[0] == definition["name"]
        for identifier, definition in enums.items():
            assert definition["members"] and identifier.split("#")[0] == definition["name"]


def test_an_option_identity_is_written_exactly_where_a_slot_has_something_to_discriminate():
    """docs/contract.md, 'Shape nodes': `id` 'is written only where the slot holds two or more options'."""
    for schema in _ALL:
        for slot in _slots(schema.to_dict()):
            assert slot, "docs/contract.md, 'Fields': shape is 'always an array, at least one'"
            for node in slot:
                assert ("id" in node) is (len(slot) > 1), node


def test_extras_come_last_and_never_sit_on_a_dataclass_option():
    """docs/contract.md, 'Shape nodes': "`extras` is last on every node… A `Struct` node never has extras"."""
    for schema in _ALL:
        for slot in _slots(schema.to_dict()):
            for node in slot:
                if node["type"] == "struct":
                    assert set(node) <= {"type", "id", "ref"}
                if "extras" in node:
                    assert list(node)[-1] == "extras"
                    # Omitted when empty: two spellings of one fact would stop
                    # the document being canonical.
                    assert node["extras"]


# --------------------------------------------- 2 — determinism, byte for byte

def test_recompiling_a_dataclass_writes_a_byte_identical_document():
    """docs/contract.md, 'Two guarantees': 'Equal definitions produce equal documents, byte for byte'."""
    rng = random.Random(31337)
    for _ in range(150):
        cls = _random_dataclass(rng, 2, defaults="some")
        first = struct_of(cls).to_dict()
        second = struct_of(cls).to_dict()
        assert first == second
        # No sort_keys: the order is the format's, not the dumper's.
        assert json.dumps(first) == json.dumps(second)


def test_a_schema_writes_the_same_document_every_time_it_is_asked():
    """docs/contract.md: 'Nothing is cached between calls' — and nothing drifts between them either."""
    for schema in _ALL:
        assert json.dumps(schema.to_dict()) == json.dumps(schema.to_dict())


# ------------------------------------------------------------ 9 — fresh trees

def test_two_to_dict_calls_share_no_container_at_any_depth():
    """docs/contract.md: 'Each call returns a fresh tree… Two callers never receive the same tree'."""
    for schema in _ALL:
        first = schema.to_dict()
        second = schema.to_dict()
        assert _containers(first).isdisjoint(_containers(second))


def test_mutating_a_document_cannot_reach_the_schema():
    """docs/contract.md: `document["defs"]["structs"].clear()` is 'harmless'."""
    for schema in _PLAIN.schemas[:60]:
        original = schema.to_dict()
        document = schema.to_dict()
        document["defs"]["structs"].clear()
        document["defs"]["enums"].clear()
        assert schema.to_dict() == original


def test_decode_hands_back_no_container_from_the_tree_it_was_given():
    """docs/decode.md, 'Fresh trees': 'never hands back a container from it'."""
    rng = random.Random(5150)
    for schema in _PLAIN.schemas:
        for _ in range(5):
            wire = _wire_for(schema, rng)
            decoded = schema.decode(wire)
            assert _containers(wire).isdisjoint(_containers(decoded))


def _wire_for(schema, rng):
    """A portable tree for one schema: sample exact Python, then write it out."""
    if type(schema) is Struct:
        instance = _sample_shape(schema, rng, 3)
        return _encode_shape(schema, instance)
    return {p.name: _encode(p.shape, _sample_options(p.shape, rng, 3))
            for p in schema.params}


# ------------------------------------------------- 4 — decode does not mutate

def test_decode_never_modifies_the_tree_it_is_given():
    """docs/decode.md, 'Fresh trees': '`decode` never modifies the tree it is given'."""
    rng = random.Random(271828)
    for schema in _ALL:
        for _ in range(8):
            wire = _wire_for(schema, rng)
            before = deepcopy(wire)
            schema.decode(wire)
            assert wire == before


def test_decode_never_modifies_a_hostile_tree_either():
    """docs/decode.md: the promise is about the tree, not about whether decode understood it."""
    rng = random.Random(1618)
    for schema in _ALL:
        for _ in range(8):
            tree = _hostile(rng, 3)
            before = deepcopy(tree)
            schema.decode(tree)
            assert tree == before


# -------------------------------------------------------- 5 — decode is total

_HOSTILE_TEXTS = ("2026-08-08", "2026-02-31", "20260808", "2026-W32-6",
                  "2026/08/08", "14:30", "14:30:00", "10:00:00.5",
                  "10:00:00+02:00", "1430", "2020", "ADMIN", "admin", "RED",
                  "", "null", "true", "3", "$type", "f0")


def _hostile(rng, depth):
    """A portable tree built to be wrong: right spellings under the wrong shapes."""
    roll = rng.random()
    if depth > 0 and roll < 0.22:
        keys = ["f0", "f1", "f2", _TYPE, _VALUE, "unknown"]
        return {rng.choice(keys): _hostile(rng, depth - 1)
                for _ in range(rng.randint(0, 4))}
    if depth > 0 and roll < 0.34:
        return [_hostile(rng, depth - 1) for _ in range(rng.randint(0, 3))]
    if roll < 0.55:
        return rng.choice(_HOSTILE_TEXTS)
    if roll < 0.7:
        return rng.randint(-5, 5)
    if roll < 0.8:
        return rng.choice((0.0, 1.5, -2.25))
    if roll < 0.9:
        return rng.random() < 0.5
    return None


def test_decode_never_raises_a_schema_error_on_any_portable_tree():
    """docs/decode.md: 'Decode never raises a schema error… that is `resolve` and `build`'."""
    rng = random.Random(80085)
    for schema in _ALL:
        for _ in range(6):
            wire = _wire_for(schema, rng)
            try:
                schema.decode(wire)
            except (SchemaTypeError, SchemaValueError) as error:
                pytest.fail(f"{schema!r} raised {error!r} on {wire!r}")


def test_decode_never_raises_at_all_on_a_hostile_tree():
    """docs/decode.md: 'a value decode cannot restore is handed back exactly as it came'."""
    rng = random.Random(60613)
    for schema in _ALL:
        for _ in range(8):
            tree = _hostile(rng, 3)
            try:
                schema.decode(tree)
            except Exception as error:  # noqa: BLE001 — any escape is the finding
                pytest.fail(f"{schema!r} raised {error!r} on {tree!r}")


def test_decode_returns_a_root_that_is_not_a_dict_exactly_as_it_came():
    """docs/decode.md, 'What decode leaves alone': 'A root that is not a dict… is returned as it came'."""
    for schema in _ALL[:80]:
        for root in (None, [1, 2], "text", 3, 3.5, True):
            assert schema.decode(root) == root


# ------------------------------------------------------------ 6 — idempotence

def test_decoding_twice_gives_what_decoding_once_gave():
    """docs/decode.md: decode restores four spellings 'and does nothing else', so a second pass has nothing left to do."""
    rng = random.Random(11235)
    for schema in _ALL:
        for _ in range(5):
            wire = _wire_for(schema, rng)
            once = schema.decode(wire)
            assert schema.decode(once) == once


def test_decoding_a_hostile_tree_twice_gives_what_decoding_once_gave():
    """docs/decode.md: an undecodable value 'is handed back exactly as it came' — including the second time."""
    rng = random.Random(31415)
    for schema in _ALL:
        for _ in range(6):
            once = schema.decode(_hostile(rng, 3))
            assert schema.decode(once) == once


# -------------------------- 3 — the document's defaults are decode's language

def _document_defaults(schema):
    document = schema.to_dict()
    if document["kind"] == "struct":
        fields = document["defs"]["structs"][document["root"]]["fields"]
    else:
        fields = document["params"]
    return {f["name"]: f["default"] for f in fields if "default" in f}


def test_every_document_default_decodes_back_to_the_certified_default():
    """docs/contract.md, 'It speaks decode's language': 'a default taken from this document is valid input to `decode`'.

    The identity is exact wherever the decoded tree can express the value: a
    dataclass stays a dict until `build` runs (docs/build.md, 'Data in, objects
    out'), and a wrapper survives decode where two options share a Python type
    (docs/decode.md, 'Unions'). Those two are checked through `build` below.
    """
    checked = 0
    broken = []
    for schema in _DEFAULTED.schemas + _MIXED.schemas + _SIGNATURES.schemas:
        fields = schema.fields if type(schema) is Struct else schema.params
        defaults = _document_defaults(schema)
        for f in fields:
            if f.name not in defaults:
                continue
            if not _decode_recovers(f.shape, f.default):
                continue
            checked += 1
            decoded = schema.decode({f.name: defaults[f.name]})[f.name]
            if decoded != f.default or type(decoded) is not type(f.default):
                broken.append(f"{schema!r}.{f.name}: {defaults[f.name]!r} "
                              f"decoded to {decoded!r}, default is {f.default!r}")

    assert checked > 200, f"only {checked} defaults exercised"
    assert broken == [], f"{len(broken)} of {checked} defaults do not round-trip:\n" + \
                         "\n".join(broken[:5])


def test_a_default_survives_json_on_the_way_from_the_document_to_decode():
    """docs/contract.md: the document is portable, so the trip through JSON must not change what decode reads."""
    for schema in _DEFAULTED.schemas:
        defaults = _document_defaults(schema)
        assert schema.decode(json.loads(json.dumps(defaults))) == schema.decode(defaults)


# Naming an option is a rule about a *slot*, not about a field: a list item and a
# field of a nested dataclass need the discriminator on the same terms the field
# does. The generative properties above and below reach these two through random
# schemas; these pin them at their smallest, because a written default that its
# own decode cannot read back is silent everywhere else.


def test_a_default_inside_a_list_names_its_option_when_the_spellings_collide():
    """docs/contract.md, 'Defaults': the default is written so 'a default taken from this document is valid input to decode'."""
    cls = make_dataclass(
        "C", [("x", list[date | time], field(default_factory=lambda: [date(2026, 8, 8)]))])
    schema = struct_of(cls)

    written = schema.to_dict()["defs"]["structs"]["C"]["fields"][0]["default"]

    assert schema.build(schema.decode({"x": written})) == schema.build({})


def test_a_default_inside_a_nested_dataclass_names_its_option_when_the_spellings_collide():
    """docs/contract.md, 'Defaults': 'Every certified default can be written this way… the encoding is total'."""
    inner = make_dataclass("Inner", [("when", date | time)])
    cls = make_dataclass(
        "Outer", [("inner", inner, field(default_factory=lambda: inner(date(2026, 8, 8))))])
    schema = struct_of(cls)

    written = schema.to_dict()["defs"]["structs"]["Outer"]["fields"][0]["default"]

    assert schema.build(schema.decode({"inner": written})) == schema.build({})


def test_building_from_the_document_defaults_equals_building_from_no_data_at_all():
    """docs/contract.md: one portable language — the written default and the certified default are the same value.

    This is the total form of the round trip: it covers the dataclass and shared
    Python type cases the exact identity above cannot state.
    """
    broken = []
    for schema in _DEFAULTED.schemas:
        from_resolve = schema.build({})
        try:
            from_document = schema.build(schema.decode(_document_defaults(schema)))
        except (SchemaTypeError, SchemaValueError) as error:
            broken.append(f"{schema!r}: build of the written defaults raised {error}")
            continue
        if from_document != from_resolve or type(from_document) is not type(from_resolve):
            broken.append(f"{schema!r}: {from_document!r} != {from_resolve!r}")

    assert broken == [], f"{len(broken)} of {len(_DEFAULTED.schemas)} schemas:\n" + \
                         "\n".join(broken[:5])


# ---------------------------------------- 7 — build does not depend on decode

def _exact_for(schema, rng):
    """An instance (or kwargs) and the exact Python tree `build` takes for it."""
    instance = _sample_shape(schema, rng, 3)
    return instance, _exact_shape(schema, instance)


def test_build_takes_an_exact_tree_with_no_decode_in_front_of_it():
    """docs/decode.md, 'Order': 'For a value already in exact Python… `decode` is unnecessary and `build` takes it directly'."""
    rng = random.Random(777)
    for schema in _PLAIN.schemas:
        for _ in range(3):
            instance, tree = _exact_for(schema, rng)
            assert schema.build(tree) == instance


def test_decode_is_a_no_op_on_an_exact_tree_and_build_cannot_tell():
    """docs/decode.md: 'nothing in an exact tree matches a portable spelling that isn't already its own'."""
    rng = random.Random(778)
    for schema in _PLAIN.schemas:
        for _ in range(3):
            _, tree = _exact_for(schema, rng)
            assert schema.decode(tree) == tree
            assert schema.build(schema.decode(tree)) == schema.build(tree)


# ---------------------------------------------- 8 — the whole wire round trip

def test_an_instance_written_to_the_wire_comes_back_as_the_same_instance():
    """docs/decode.md: 'JSON text ─loads─▶ portable tree ─decode─▶ exact Python tree ─build─▶ objects'."""
    rng = random.Random(2718281)
    for schema in _PLAIN.schemas:
        for _ in range(5):
            instance = _sample_shape(schema, rng, 3)
            wire = _encode_shape(schema, instance)
            rebuilt = schema.build(schema.decode(json.loads(json.dumps(wire))))
            assert rebuilt == instance
            assert type(rebuilt) is type(instance)


def test_the_wire_round_trip_holds_for_signatures_too():
    """docs/contract.md, 'Documents': a signature carries the same language, written in place."""
    rng = random.Random(2718282)
    for schema in _SIGNATURES.schemas:
        for _ in range(5):
            values = {p.name: _sample_options(p.shape, rng, 3) for p in schema.params}
            wire = {p.name: _encode(p.shape, values[p.name]) for p in schema.params}
            rebuilt = schema.build(schema.decode(json.loads(json.dumps(wire))))
            assert rebuilt == values


# -------------------------------------------------------- hypothesis property

# One curated option per portable spelling, so a union drawn from this pool is
# always a legal one: no two entries share an option identity.
_KIND_HINTS = {
    "int": int, "float": float, "str": str, "bool": bool, "date": date,
    "time": time, "role": _Role, "status": _Status,
    "list_str": list[str], "list_int": list[int],
}
_KIND_VALUES = {
    "int": 7, "float": 2.5, "str": "abc", "bool": True,
    "date": date(2026, 8, 8), "time": time(14, 30),
    "role": _Role.ADMIN, "status": _Status.OPEN,
    "list_str": ["a"], "list_int": [1],
}
_KIND_WIRE = {
    "int": 7, "float": 2.5, "str": "abc", "bool": True,
    "date": "2026-08-08", "time": "14:30:00",
    "role": "ADMIN", "status": "OPEN",
    "list_str": ["a"], "list_int": [1],
}
_KIND_WIRE_KINDS = {
    "int": (int,), "float": (float, int), "str": (str,), "bool": (bool,),
    "date": (str,), "time": (str,), "role": (str,), "status": (str,),
    "list_str": (list,), "list_int": (list,),
}
_KIND_PYTYPES = {
    "int": int, "float": float, "str": str, "bool": bool, "date": date,
    "time": time, "role": _Role, "status": _Status,
    "list_str": list, "list_int": list,
}
_KIND_IDS = {
    "int": "int", "float": "float", "str": "str", "bool": "bool",
    "date": "date", "time": "time", "role": "_Role", "status": "_Status",
    "list_str": "list[str]", "list_int": "list[int]",
}
_KINDS = tuple(_KIND_HINTS)

_UNIONS = st.lists(st.sampled_from(_KINDS), min_size=2, max_size=3, unique=True)
_OPTIONALS = st.booleans()


def _union_schema(kinds, optional=False):
    hint = reduce(or_, [_KIND_HINTS[k] for k in kinds])
    if optional:
        hint = hint | None
    return struct_of(make_dataclass("C", [("x", hint)]))


def _readers(kinds, wire):
    """The options that can be spelled the way `wire` is spelled."""
    return [k for k in kinds if type(wire) in _KIND_WIRE_KINDS[k]]


@settings(deadline=None, max_examples=300)
@given(kinds=_UNIONS, optional=_OPTIONALS)
def test_a_bare_value_decodes_exactly_when_one_option_can_be_spelled_that_way(kinds, optional):
    """docs/decode.md, 'Unions': 'A value is decoded into an option when exactly one option can be spelled that way'.

    Where the spellings collide, 'nothing is decoded' and the value stands as it
    came — so the reading is decided by the schema, never by the text.
    """
    schema = _union_schema(kinds, optional)

    for kind in kinds:
        wire = _KIND_WIRE[kind]
        decoded = schema.decode({"x": wire})["x"]

        if len(_readers(kinds, wire)) == 1:
            expected = _KIND_VALUES[kind]
            assert decoded == expected and type(decoded) is type(expected)
        else:
            assert decoded == wire and type(decoded) is type(wire)


@settings(deadline=None, max_examples=300)
@given(kinds=_UNIONS)
def test_a_named_option_is_consumed_unless_validation_still_needs_the_name(kinds):
    """docs/decode.md, 'Unions': options sharing a Python type keep the wrapper; options sharing only a spelling consume it.

    And where nothing collides the wrapper is 'an ordinary foreign dictionary',
    handed back for `build` to report.
    """
    schema = _union_schema(kinds)

    for kind in kinds:
        wrapper = {_TYPE: _KIND_IDS[kind], _VALUE: _KIND_WIRE[kind]}
        decoded = schema.decode({"x": wrapper})["x"]

        collides = any(other != kind and set(_KIND_WIRE_KINDS[other]) & set(_KIND_WIRE_KINDS[kind])
                       for other in kinds)
        shares_python_type = any(other != kind and _KIND_PYTYPES[other] is _KIND_PYTYPES[kind]
                                 for other in kinds)

        if not collides:
            assert decoded == wrapper
        elif shares_python_type:
            assert decoded == {_TYPE: _KIND_IDS[kind], _VALUE: _KIND_VALUES[kind]}
        else:
            expected = _KIND_VALUES[kind]
            assert decoded == expected and type(decoded) is type(expected)


@settings(deadline=None, max_examples=300)
@given(kinds=_UNIONS)
def test_the_spelling_the_document_prescribes_always_reaches_build_intact(kinds):
    """docs/contract.md, 'Reading the wire from the document': 'The named spelling always works'.

    Named where two options share a portable spelling, bare everywhere else —
    a wrapper outside that case is 'just a foreign dictionary' (docs/build.md).
    """
    schema = _union_schema(kinds)

    for kind in kinds:
        collides = any(other != kind and set(_KIND_WIRE_KINDS[other]) & set(_KIND_WIRE_KINDS[kind])
                       for other in kinds)
        sent = ({_TYPE: _KIND_IDS[kind], _VALUE: _KIND_WIRE[kind]} if collides
                else _KIND_WIRE[kind])

        built = schema.build(schema.decode(json.loads(json.dumps({"x": sent}))))

        assert built.x == _KIND_VALUES[kind]
        assert type(built.x) is _KIND_PYTYPES[kind]


@settings(deadline=None, max_examples=200)
@given(kinds=_UNIONS, optional=_OPTIONALS)
def test_a_document_default_decodes_and_builds_back_to_the_value_it_was_written_from(kinds, optional):
    """docs/contract.md, 'Defaults': the default is written 'in the portable language of decode.md'."""
    kind = kinds[0]
    value = _KIND_VALUES[kind]
    hint = reduce(or_, [_KIND_HINTS[k] for k in kinds])
    if optional:
        hint = hint | None
    schema = struct_of(make_dataclass("C", [("x", hint, _default_spec(value))]))

    written = schema.to_dict()["defs"]["structs"]["C"]["fields"][0]["default"]

    assert schema.build(schema.decode({"x": written})).x == value
    assert schema.build({}).x == value


_TEXTS = ("2026-08-08", "2026-02-31", "20260808", "2026-W32-6",
          "2026-08-08T10:00", "2026/08/08", "14:30", "14:30:00",
          "10:00:00.5", "10:00:00+02:00", "1430", "143000", "2020",
          "ADMIN", "USER", "RED", "BLUE", "", "hello")


@settings(deadline=None, max_examples=100)
@given(text=st.sampled_from(_TEXTS))
def test_a_str_option_reads_text_as_text_however_much_it_looks_like_something_else(text):
    """docs/decode.md: 'A `str` field holding "2026-08-08" stays a `str`… The shape decides the reading; the text never does'."""
    schema = struct_of(make_dataclass("C", [("x", str)]))

    decoded = schema.decode({"x": text})["x"]

    assert type(decoded) is str
    assert decoded == text


@settings(deadline=None, max_examples=100)
@given(text=st.sampled_from(_TEXTS))
def test_no_text_is_ever_read_as_both_a_date_and_a_time(text):
    """docs/decode.md, 'Canonical spellings': 'the accepted spellings are fixed, and they are disjoint'."""
    as_date = struct_of(make_dataclass("D", [("x", date)])).decode({"x": text})["x"]
    as_time = struct_of(make_dataclass("T", [("x", time)])).decode({"x": text})["x"]

    assert not (type(as_date) is date and type(as_time) is time)


@settings(deadline=None, max_examples=200)
@given(kinds=_UNIONS, text=st.sampled_from(_TEXTS))
def test_an_undecodable_payload_leaves_its_wrapper_standing(kinds, text):
    """docs/decode.md, 'Unions': 'A wrapper whose payload did not reach the option it named is also left alone'."""
    schema = _union_schema(kinds)

    for kind in kinds:
        if _KIND_WIRE_KINDS[kind] != (str,) or kind == "str":
            continue
        wrapper = {_TYPE: _KIND_IDS[kind], _VALUE: text}
        decoded = schema.decode({"x": wrapper})["x"]

        reached = type(decoded) is _KIND_PYTYPES[kind]
        assert reached or decoded == wrapper

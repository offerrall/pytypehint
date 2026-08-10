"""Defaults and the round trip the portable contract promises.

The property under attack is the one contract.md states as
`build(decode(written))` returning the default it started from:

    to_dict() -> field["default"] -> decode() -> build()

and the answer has to match the default the recipe serves, in **value, exact
type, and chosen union branch** — a `date` may not come back as `str`, a member
of one enum may not come back as a member of another, an `int` may not come back
as a `float`. Contract: docs/contract.md ("It speaks decode's language",
"Defaults"), docs/decode.md, docs/defaults.md.

Two supporting promises are checked beside it: the document shares no mutable
object with the schema's certified defaults, and two servings of one default
share no container.
"""

import copy
import json
import random
from dataclasses import dataclass, field, fields as dc_fields, make_dataclass
from datetime import date, time
from enum import Enum, IntEnum, StrEnum
from typing import Annotated

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from pytypehint import (
    Bool, Date, EnumShape, Field, Float, Int, List, Max, Min, NoneShape, Str,
    Struct, Time, signature_of, struct_of,
)

# ---------------------------------------------------------------------------
# The round trip, stated once
# ---------------------------------------------------------------------------


def _document_defaults(document):
    """Every default the document publishes for the root's own slots."""
    if document["kind"] == "struct":
        fields = document["defs"]["structs"][document["root"]]["fields"]
    else:
        fields = document["params"]
    return {f["name"]: f["default"] for f in fields if "default" in f}


def _same(left, right, path=()):
    """Deep equality that also demands the exact type and enum identity."""
    where = ".".join(map(str, path)) or "<root>"
    assert type(left) is type(right), (
        f"{where}: {type(left).__name__} != {type(right).__name__} "
        f"({left!r} vs {right!r})")
    if isinstance(left, Enum):
        assert left is right, f"{where}: {left!r} is not {right!r}"
    elif type(left) is list:
        assert len(left) == len(right), f"{where}: {len(left)} != {len(right)} items"
        for i, (a, b) in enumerate(zip(left, right)):
            _same(a, b, (*path, i))
    elif hasattr(left, "__dataclass_fields__"):
        for f in dc_fields(left):
            _same(getattr(left, f.name), getattr(right, f.name), (*path, f.name))
    else:
        assert left == right, f"{where}: {left!r} != {right!r}"


def round_trip(schema, supplied=None):
    """Assert the document's defaults rebuild exactly what the recipes serve.

    Runs the trip three ways: straight from the document, through a real JSON
    text, and with a random half of the document's defaults left out so the
    recipe serves those instead. All three must land on the same object.
    """
    supplied = supplied or {}
    document = schema.to_dict()
    written = _document_defaults(document)
    expected = schema.build(dict(supplied))

    _same(expected, schema.build(schema.decode({**written, **supplied})))

    hopped = _document_defaults(json.loads(json.dumps(document)))
    _same(expected, schema.build(schema.decode({**hopped, **supplied})))

    rnd = random.Random(len(json.dumps(document)))
    half = {k: v for k, v in written.items() if rnd.random() < 0.5}
    _same(expected, schema.build(schema.decode({**half, **supplied})))
    return expected


# ---------------------------------------------------------------------------
# Vocabulary used by the cases below
# ---------------------------------------------------------------------------


class Role(Enum):
    ADMIN = "a"
    USER = "u"


class Status(Enum):
    OPEN = 1
    SHUT = 2


class Level(IntEnum):
    LOW = 1
    HIGH = 9


class Tag(StrEnum):
    RED = "red"
    BLUE = "blue"


class Crossed(Enum):
    # "RED" names one member and is the value of the other: reading a member by
    # value instead of by name is silent, so the round trip has to pin it.
    RED = "BLUE"
    BLUE = "RED"


class Aliased(Enum):
    A = 1
    B = 2
    ALIAS = 1


@dataclass
class Leaf:
    n: int = 1
    d: date = date(2000, 1, 1)


@dataclass
class Shipped:
    on: date = date(2026, 2, 2)


@dataclass
class Cancelled:
    reason: str = "x"


# ---------------------------------------------------------------------------
# One default shape at a time
# ---------------------------------------------------------------------------


def test_scalar_defaults_round_trip():
    @dataclass
    class Scalars:
        i: int = 3
        big: int = 10 ** 30
        f: float = 1.5
        whole: float = 2.0
        neg_zero: float = -0.0
        s: str = "hi"
        empty: str = ""
        t: bool = True
        f_: bool = False
        d: date = date(2026, 8, 8)
        first_day: date = date(1, 1, 1)
        tm: time = time(14, 30)
        midnight: time = time(0, 0, 0)

    built = round_trip(struct_of(Scalars))
    assert type(built.whole) is float
    assert type(built.i) is int
    assert type(built.t) is bool


def test_none_default_and_optional_slots():
    @dataclass
    class Nones:
        a: int | None = None
        b: str | None = None
        d: date | None = None
        e: Role | None = None
        lst: list[int] | None = None
        nested: Leaf | None = None
        filled: date | None = date(2020, 1, 1)

    document = struct_of(Nones).to_dict()
    written = _document_defaults(document)
    # null appears in the format for exactly one reason: the default is None.
    assert written["a"] is None and written["nested"] is None
    built = round_trip(struct_of(Nones))
    assert built.a is None and built.nested is None


def test_list_defaults_round_trip():
    @dataclass
    class Lists:
        empty: list[int] = field(default_factory=list)
        ints: list[int] = field(default_factory=lambda: [1, 2, 3])
        floats: list[float] = field(default_factory=lambda: [1.0, 2.5])
        dates: list[date] = field(default_factory=lambda: [date(2026, 1, 1)])
        times: list[time] = field(default_factory=lambda: [time(9, 0)])
        roles: list[Role] = field(default_factory=lambda: [Role.ADMIN, Role.USER])
        nested: list[list[int]] = field(default_factory=lambda: [[1], []])
        bools: list[bool] = field(default_factory=lambda: [True, False])

    built = round_trip(struct_of(Lists))
    assert built.empty == [] and built.nested[1] == []
    assert all(type(x) is float for x in built.floats)
    assert all(type(x) is date for x in built.dates)


def test_enum_defaults_keep_their_member():
    @dataclass
    class Enums:
        r: Role = Role.ADMIN
        s: Status = Status.SHUT
        lv: Level = Level.HIGH
        tg: Tag = Tag.BLUE
        crossed: Crossed = Crossed.RED
        alias: Aliased = Aliased.ALIAS
        lst: list[Crossed] = field(
            default_factory=lambda: [Crossed.RED, Crossed.BLUE])

    written = _document_defaults(struct_of(Enums).to_dict())
    # by member name, and by the canonical name for an alias
    assert written["crossed"] == "RED"
    assert written["alias"] == "A"
    built = round_trip(struct_of(Enums))
    assert built.crossed is Crossed.RED
    assert built.alias is Aliased.A
    assert built.lst == [Crossed.RED, Crossed.BLUE]
    assert type(built.lv) is Level and type(built.tg) is Tag


def test_date_and_time_defaults_use_the_canonical_spelling():
    @dataclass
    class When:
        d: date = date(2026, 8, 8)
        early: date = date(1, 2, 3)
        t: time = time(14, 30)
        seconds: time = time(23, 59, 59)

    written = _document_defaults(struct_of(When).to_dict())
    assert written == {"d": "2026-08-08", "early": "0001-02-03",
                       "t": "14:30:00", "seconds": "23:59:59"}
    round_trip(struct_of(When))


def test_nested_dataclass_default_round_trips():
    @dataclass
    class Mid:
        leaf: Leaf = field(default_factory=Leaf)
        tag: Role = Role.USER

    @dataclass
    class Top:
        mid: Mid = field(default_factory=Mid)
        items: list[Leaf] = field(default_factory=lambda: [Leaf(2)])

    built = round_trip(struct_of(Top))
    assert type(built.mid) is Mid and type(built.mid.leaf) is Leaf
    assert type(built.mid.leaf.d) is date


def test_defaults_four_levels_down():
    @dataclass
    class L4:
        v: int = 4
        d: date = date(2004, 4, 4)

    @dataclass
    class L3:
        a: L4 = field(default_factory=L4)
        r: Role = Role.ADMIN

    @dataclass
    class L2:
        a: L3 = field(default_factory=L3)
        w: str | date = date(2002, 2, 2)

    @dataclass
    class L1:
        a: L2 = field(default_factory=L2)
        lst: list[L2] = field(default_factory=lambda: [L2()])

    built = round_trip(struct_of(L1))
    assert type(built.a.a.a.d) is date
    assert type(built.a.w) is date
    assert type(built.lst[0].w) is date


def test_nested_required_field_is_supplied_by_the_written_default():
    @dataclass
    class Inner:
        req: int
        opt: str = "o"

    @dataclass
    class Outer:
        inner: Inner = field(default_factory=lambda: Inner(5))
        lst: list[Inner] = field(default_factory=lambda: [Inner(6, "z")])

    written = _document_defaults(struct_of(Outer).to_dict())
    # a written dataclass default carries every field, defaulted or not, so the
    # object it describes can be constructed with nothing else
    assert written["inner"] == {"req": 5, "opt": "o"}
    round_trip(struct_of(Outer))


@dataclass
class Node:
    v: int = 0
    nxt: "Node | None" = None
    kids: "list[Node]" = field(default_factory=list)


@dataclass
class NodeHolder:
    root: Node = field(default_factory=lambda: Node(1, Node(2, Node(3))))


def test_recursive_default_round_trips():
    Holder = NodeHolder
    written = _document_defaults(struct_of(Holder).to_dict())
    assert written["root"]["nxt"]["nxt"]["v"] == 3
    built = round_trip(struct_of(Holder))
    assert built.root.nxt.nxt.v == 3
    round_trip(struct_of(Node))


# ---------------------------------------------------------------------------
# Unions: the branch has to survive, and it is what the wrapper is for
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("annotation, default, expect", [
    (int | float, 10, {"$type": "int", "$value": 10}),
    (int | float, 10.0, {"$type": "float", "$value": 10.0}),
    (str | date, "2026-08-08", {"$type": "str", "$value": "2026-08-08"}),
    (str | date, date(2026, 8, 8), {"$type": "date", "$value": "2026-08-08"}),
    (date | time, time(9, 30), {"$type": "time", "$value": "09:30:00"}),
    (Role | Status, Status.OPEN, {"$type": "Status", "$value": "OPEN"}),
    (Role | str, "ADMIN", {"$type": "str", "$value": "ADMIN"}),
    (Role | str, Role.ADMIN, {"$type": "Role", "$value": "ADMIN"}),
    (Tag | str, Tag.RED, {"$type": "Tag", "$value": "RED"}),
    (Tag | str, "RED", {"$type": "str", "$value": "RED"}),
    (int | None, None, None),
    (bool | int, True, True),
    (bool | int, 1, 1),
    (Level | int, Level.LOW, "LOW"),
    (Level | int, 1, 1),
])
def test_colliding_slot_names_its_option(annotation, default, expect):
    """Where two options share a portable spelling the written default carries
    the wrapper decode consumes; where nothing collides it stays bare."""
    def fn(x=default):
        ...
    fn.__annotations__ = {"x": annotation}
    schema = signature_of(fn)

    assert _document_defaults(schema.to_dict()) == {"x": expect}
    built = round_trip(schema)
    _same(default, built["x"])


def test_union_of_lists_keeps_the_validation_wrapper():
    @dataclass
    class UnionLists:
        strs: list[str] | list[int] = field(default_factory=lambda: ["a"])
        ints: list[str] | list[int] = field(default_factory=lambda: [1])
        empty: list[str] | list[int] = field(default_factory=list)

    written = _document_defaults(struct_of(UnionLists).to_dict())
    assert written["strs"] == {"$type": "list[str]", "$value": ["a"]}
    assert written["ints"] == {"$type": "list[int]", "$value": [1]}
    built = round_trip(struct_of(UnionLists))
    assert type(built.ints[0]) is int and type(built.strs[0]) is str


def test_the_option_rule_reaches_every_slot():
    """The regression the release found: a `date` inside `list[str | date]` was
    written bare, which decode is right to leave as text and build then filed
    under the `str` option in silence. The rule is about a slot, so it holds for
    a list element and for a field of a nested dataclass too."""
    @dataclass
    class Nested:
        w: str | date = date(2024, 6, 1)
        n: int | float = 10
        t: date | time = time(9, 0)

    @dataclass
    class Slots:
        own: str | date = date(2024, 6, 1)
        item: list[str | date] = field(
            default_factory=lambda: [date(2024, 6, 1)])
        deeper: list[list[str | date]] = field(
            default_factory=lambda: [[date(2024, 6, 1)]])
        inside: Nested = field(default_factory=Nested)
        deep_struct: list[Nested] = field(default_factory=lambda: [Nested()])

    stamp = {"$type": "date", "$value": "2024-06-01"}
    written = _document_defaults(struct_of(Slots).to_dict())
    assert written["own"] == stamp
    assert written["item"] == [stamp]
    assert written["deeper"] == [[stamp]]
    assert written["inside"]["w"] == stamp
    assert written["deep_struct"][0]["w"] == stamp

    built = round_trip(struct_of(Slots))
    assert type(built.item[0]) is date
    assert type(built.deeper[0][0]) is date
    assert type(built.inside.w) is date
    assert type(built.inside.n) is int
    assert type(built.inside.t) is time

    # and the bare spelling would indeed have been filed under `str`
    schema = struct_of(Slots)
    assert schema.decode({"item": ["2024-06-01"]}) == {"item": ["2024-06-01"]}


def test_list_of_union_defaults():
    @dataclass
    class ListUnion:
        numbers: list[int | float] = field(default_factory=lambda: [1, 2.0, 3.5])
        texts: list[str | date] = field(
            default_factory=lambda: ["x", date(2026, 1, 1), "2026-01-01"])
        members: list[Role | Status] = field(
            default_factory=lambda: [Role.ADMIN, Status.OPEN])
        nullable: list[int | None] = field(default_factory=lambda: [1, None])
        flags: list[bool | int] = field(default_factory=lambda: [True, 1])

    built = round_trip(struct_of(ListUnion))
    assert [type(v) for v in built.numbers] == [int, float, float]
    assert [type(v) for v in built.texts] == [str, date, str]
    assert [type(v) for v in built.members] == [Role, Status]
    assert [type(v) for v in built.flags] == [bool, int]


def test_dataclass_options_use_the_inline_discriminator():
    @dataclass
    class Order:
        event: Shipped | Cancelled = field(default_factory=Shipped)
        other: Shipped | Cancelled = field(default_factory=Cancelled)
        lst: list[Shipped | Cancelled] = field(
            default_factory=lambda: [Shipped(), Cancelled()])
        beside_scalar: Shipped | int = 3
        nothing: Shipped | Cancelled | None = None

    written = _document_defaults(struct_of(Order).to_dict())
    assert written["event"] == {"$type": "Shipped", "on": "2026-02-02"}
    assert written["other"] == {"$type": "Cancelled", "reason": "x"}
    assert written["lst"][1]["$type"] == "Cancelled"
    # one dataclass option needs no discriminator
    assert written["beside_scalar"] == 3

    built = round_trip(struct_of(Order))
    assert type(built.event) is Shipped and type(built.other) is Cancelled
    assert [type(v) for v in built.lst] == [Shipped, Cancelled]


def test_dataclass_default_carrying_a_union():
    @dataclass
    class HasUnion:
        v: int | float = 7
        w: str | date = date(2021, 5, 5)
        x: Role | Status = Status.SHUT
        y: list[str] | list[int] = field(default_factory=lambda: [2])

    @dataclass
    class Wraps:
        inner: HasUnion = field(default_factory=HasUnion)
        lst: list[HasUnion] = field(
            default_factory=lambda: [HasUnion(v=1.0)])

    built = round_trip(struct_of(Wraps))
    assert type(built.inner.v) is int and type(built.lst[0].v) is float
    assert type(built.inner.w) is date and built.inner.x is Status.SHUT
    assert type(built.inner.y[0]) is int


def test_branch_chosen_by_acceptance_survives_the_document():
    """Two list options can both hold a list, so the branch is decided by what
    each accepts. Whatever the value router picked, the document must name it."""
    @dataclass
    class Chooser:
        a: list[str] | list[date] = field(
            default_factory=lambda: [date(2026, 8, 8)])
        b: list[str] | list[date] = field(default_factory=lambda: ["x"])
        c: list[float] | list[int] = field(default_factory=lambda: [1])
        d: list[float] | list[int] = field(default_factory=lambda: [1.0])

    written = _document_defaults(struct_of(Chooser).to_dict())
    assert written["a"]["$type"] == "list[date]"
    assert written["b"]["$type"] == "list[str]"
    assert written["c"]["$type"] == "list[int]"
    assert written["d"]["$type"] == "list[float]"
    built = round_trip(struct_of(Chooser))
    assert type(built.a[0]) is date and type(built.b[0]) is str
    assert type(built.c[0]) is int and type(built.d[0]) is float


def test_constrained_option_decides_the_branch():
    @dataclass
    class Constrained:
        # the first option refuses a one-item list, so the branch is the second
        picky: Annotated[list[int], Min(value=2)] | list[int | str] = field(
            default_factory=lambda: [1])
        # both accept, and the author's order decides
        both: Annotated[list[int], Max(value=3)] | list[int | str] = field(
            default_factory=lambda: [1, 2])

    written = _document_defaults(struct_of(Constrained).to_dict())
    assert written["picky"] == {"$type": "list[int | str]", "$value": [1]}
    assert written["both"] == {"$type": "list[int]", "$value": [1, 2]}
    round_trip(struct_of(Constrained))


def test_homonym_enums_and_structs_keep_their_own_class():
    """Two classes of one name sit in one document under different ids. A member
    of one may not come back resolved against the other."""
    first = Enum("Same", {"A": 1, "B": 2})
    second = Enum("Same", {"A": "x", "C": "y"})
    target_a = make_dataclass("Target", [("n", int, field(default=1))])
    target_b = make_dataclass("Target", [("s", str, field(default="z"))])

    @dataclass
    class Homonyms:
        e1: first = first.B
        e2: second = second.A
        lst: list[second] = field(default_factory=lambda: [second.C])
        s1: target_a = field(default_factory=lambda: target_a(5))
        s2: target_b = field(default_factory=lambda: target_b("q"))

    document = struct_of(Homonyms).to_dict()
    assert sorted(document["defs"]["enums"]) == ["Same", "Same#2"]
    assert sorted(document["defs"]["structs"]) == ["Homonyms", "Target", "Target#2"]

    built = round_trip(struct_of(Homonyms))
    assert built.e1 is first.B and type(built.e1) is first
    assert built.e2 is second.A and type(built.e2) is second
    assert built.lst == [second.C]
    assert type(built.s1) is target_a and type(built.s2) is target_b


def test_dataclass_and_enum_of_one_name_in_one_slot():
    """The core admits the pair: they have separate discriminators. A default
    from either side has to reach its own option."""
    shared_name = make_dataclass("Coin", [("n", int, field(default=1))])
    coin_enum = Enum("Coin", {"HEADS": 1, "TAILS": 2})

    @dataclass
    class Holder:
        x: object = None

    options = (
        Struct(cls=shared_name,
               fields=(Field(name="n", shape=(Int(),), default=1),)),
        EnumShape(cls=coin_enum),
    )
    from_enum = Struct(cls=Holder, fields=(
        Field(name="x", shape=options, default=coin_enum.TAILS),))
    from_struct = Struct(cls=Holder, fields=(
        Field(name="x", shape=options, default=shared_name(3)),))

    assert _document_defaults(from_enum.to_dict()) == {"x": "TAILS"}
    assert _document_defaults(from_struct.to_dict()) == {"x": {"n": 3}}
    assert round_trip(from_enum).x is coin_enum.TAILS
    assert type(round_trip(from_struct).x) is shared_name


@pytest.mark.parametrize("shape, default", [
    ((Date(), Str()), "2026-08-08"),
    ((Date(), Str()), date(2026, 8, 8)),
    ((Float(), Int()), 5),
    ((Float(), Int()), 5.0),
    ((Time(), Date(), Str()), time(1, 2, 3)),
    ((Time(), Date(), Str()), date(2, 2, 2)),
    ((Time(), Date(), Str()), "x"),
    ((NoneShape(), Int()), None),
    ((Bool(), Float()), True),
    ((List(item=(Str(),)), List(item=(Int(),))), []),
    ((List(item=(Int(),)), List(item=(Str(),))), [1]),
])
def test_hand_built_option_order_does_not_change_the_reading(shape, default):
    """The compiler writes union options in the author's order; a hand-built
    schema may order them any way. The written default still names its own."""
    @dataclass
    class Holder:
        x: object = None

    schema = Struct(cls=Holder,
                    fields=(Field(name="x", shape=shape, default=default),))
    _same(default, round_trip(schema).x)


# ---------------------------------------------------------------------------
# Freshness: the document owns nothing, and two servings share nothing
# ---------------------------------------------------------------------------


def _mutable_schema():
    @dataclass
    class Mut:
        lst: list[int] = field(default_factory=lambda: [1, 2])
        nested: list[list[int]] = field(default_factory=lambda: [[1]])
        inner: Leaf = field(default_factory=Leaf)
        lofd: list[Leaf] = field(default_factory=lambda: [Leaf(5)])
        wrapped: list[str] | list[int] = field(default_factory=lambda: [1])

    return struct_of(Mut)


def test_document_shares_no_container_with_the_certified_default():
    schema = _mutable_schema()
    written = _document_defaults(schema.to_dict())
    by_name = {f.name: f for f in schema.fields}
    assert written["lst"] is not by_name["lst"].default
    assert written["nested"][0] is not by_name["nested"].default[0]
    assert written["lofd"][0] is not by_name["lofd"].default[0]
    # two documents never hand out one tree either
    other = _document_defaults(schema.to_dict())
    assert written["lst"] is not other["lst"]


def test_wrecking_the_document_leaves_the_schema_and_later_builds_intact():
    schema = _mutable_schema()
    before = json.dumps(schema.to_dict())
    expected = schema.build({})

    document = schema.to_dict()
    for node in _document_defaults(document).values():
        _wreck(node)
    document["defs"]["structs"].clear()

    assert json.dumps(schema.to_dict()) == before
    _same(expected, schema.build({}))
    _same(expected, schema.build(schema.decode(_document_defaults(schema.to_dict()))))


def _wreck(node):
    if type(node) is dict:
        for value in list(node.values()):
            _wreck(value)
        node["WRECKED"] = "x"
    elif type(node) is list:
        for value in list(node):
            _wreck(value)
        node.append("WRECKED")


@pytest.mark.parametrize("source", ["recipe", "document"])
def test_two_servings_of_one_default_share_no_container(source):
    schema = _mutable_schema()
    if source == "recipe":
        first, second = schema.build({}), schema.build({})
    else:
        written = _document_defaults(schema.to_dict())
        first = schema.build(schema.decode(written))
        second = schema.build(schema.decode(_document_defaults(schema.to_dict())))

    by_name = {f.name: f for f in schema.fields}
    assert first.lst is not second.lst
    assert first.lst is not by_name["lst"].default
    assert first.nested[0] is not second.nested[0]
    assert first.inner is not second.inner
    assert first.lofd[0] is not second.lofd[0]
    assert first.wrapped is not second.wrapped

    first.lst.append(99)
    first.nested[0].append(99)
    first.inner.n = 99
    first.lofd[0].n = 99
    _same(schema.build({}), second)


def test_aliasing_inside_a_default_is_not_preserved():
    """A portable tree has no aliases to carry, and build constructs separate
    objects anyway — so one object written twice comes back as two."""
    inner = [1, 2]
    leaf = Leaf(3)

    def fn(lists: list[list[int]] = [inner, inner],
           leaves: list[Leaf] = [leaf, leaf]):
        ...

    schema = signature_of(fn)
    built = round_trip(schema)
    assert built["lists"][0] is not built["lists"][1]
    assert built["lists"][0] is not inner
    assert built["leaves"][0] is not built["leaves"][1]
    assert built["leaves"][0] is not leaf

    written = _document_defaults(schema.to_dict())
    assert written["lists"][0] is not written["lists"][1]
    assert written["leaves"][0] is not written["leaves"][1]


def test_shared_recipe_object_is_rematerialized_per_serving():
    """Several defaults may name one object. Each serving reconstructs it, so
    nobody receives the recipe itself."""
    shared_list = [1, 2]
    shared_leaf = Leaf(9)

    def fn(a: list[int] = shared_list, b: list[int] = shared_list,
           c: Leaf = shared_leaf, d: Leaf = shared_leaf):
        ...

    schema = signature_of(fn)
    built = round_trip(schema)
    assert built["a"] == built["b"] == [1, 2]
    assert built["a"] is not built["b"]
    assert built["a"] is not shared_list
    assert built["c"] is not built["d"]
    assert built["c"] is not shared_leaf
    assert built["c"] == built["d"] == Leaf(9)


# ---------------------------------------------------------------------------
# decode alone, and the two exceptions contract.md names
# ---------------------------------------------------------------------------


def test_decode_alone_lands_on_the_value_outside_the_two_exceptions():
    @dataclass
    class Exact:
        i: int = 1
        f: float = 2.0
        s: str = "s"
        b: bool = True
        d: date = date(2026, 8, 8)
        t: time = time(14, 30)
        r: Role = Role.ADMIN
        n: int | None = None
        u: int | float = 3
        sd: str | date = date(2021, 1, 1)
        lst: list[date] = field(default_factory=lambda: [date(2020, 1, 1)])
        deep: list[list[str | date]] = field(
            default_factory=lambda: [[date(2020, 1, 1)]])

    schema = struct_of(Exact)
    prepared = schema.decode(_document_defaults(schema.to_dict()))
    for f in schema.fields:
        _same(f.default, prepared[f.name], (f.name,))


def test_the_two_exceptions_survive_decode_and_are_removed_by_build():
    @dataclass
    class Surviving:
        lists: list[str] | list[int] = field(default_factory=lambda: [1])
        nested: Leaf = field(default_factory=Leaf)
        routed: Shipped | Cancelled = field(default_factory=Shipped)

    schema = struct_of(Surviving)
    prepared = schema.decode(_document_defaults(schema.to_dict()))
    # a slot whose options share a Python type keeps its wrapper
    assert prepared["lists"] == {"$type": "list[int]", "$value": [1]}
    # a nested dataclass stays a dict, keeping its inline $type where it had one
    assert prepared["nested"] == {"n": 1, "d": date(2000, 1, 1)}
    assert prepared["routed"] == {"$type": "Shipped", "on": date(2026, 2, 2)}
    built = schema.build(prepared)
    assert built.lists == [1] and type(built.nested) is Leaf
    assert type(built.routed) is Shipped


# ---------------------------------------------------------------------------
# Signature parameters
# ---------------------------------------------------------------------------


def test_signature_parameter_defaults_round_trip():
    def upload(a: int = 1, b: float = 2.0, c: str = "s",
               d: date = date(2026, 3, 3), e: time = time(8, 0),
               f: Role = Role.ADMIN, g: list[int] = [1, 2], h: Leaf = Leaf(3),
               i: int | float = 4, j: str | date = date(2020, 2, 2),
               k: list[str] | list[int] = [1],
               m: Shipped | Cancelled = Shipped(), n: int | None = None,
               o: list[int] = [], *, p: list[Leaf] = [Leaf(1)],
               q: list[list[str]] = [["a"], []]):
        """Upload a document."""

    schema = signature_of(upload)
    built = round_trip(schema)
    assert type(built["d"]) is date and type(built["h"]) is Leaf
    assert type(built["j"]) is date and type(built["m"]) is Shipped
    assert built["o"] == [] and built["q"] == [["a"], []]


def test_signature_defaults_beside_required_parameters():
    def report(when: date, who: Role, note: str = "n",
               at: date | str = date(2020, 1, 1),
               tags: list[str] | list[int] = ["a"]):
        ...

    schema = signature_of(report)
    supplied = {"when": date(1999, 9, 9), "who": Role.USER}
    built = round_trip(schema, supplied)
    assert built["when"] == date(1999, 9, 9) and built["who"] is Role.USER
    assert type(built["at"]) is date and type(built["tags"][0]) is str


# ---------------------------------------------------------------------------
# Mass generation: build random schemas, derive the expectation from the
# document, and run the whole trip
# ---------------------------------------------------------------------------

_STRS = ["", "a", "2026-08-08", "14:30", "14:30:00", "A", "B", "true", "null",
         "3", "$type", "list[int]", "None", "20260808", "2026-02-31"]
_INTS = [0, 1, -1, 7, 10 ** 20]
_FLOATS = [0.0, -0.0, 1.0, -1.5, 2.0, 1e300]
_DATES = [date(1, 1, 1), date(2026, 8, 8), date(9999, 12, 31)]
_TIMES = [time(0, 0, 0), time(14, 30, 0), time(23, 59, 59)]


class _Schemas:
    """Random schemas whose every field carries a default.

    Option identities are kept distinct as they are generated, so every union
    the compiler is offered is one it accepts.
    """

    def __init__(self, rnd):
        self.rnd = rnd
        self.n = 0
        self.specs = {}

    def _name(self, stem):
        self.n += 1
        return f"{stem}{self.n}"

    def key(self, node):
        if node[0] == "enum":
            return node[1].__name__
        if node[0] == "struct":
            return "struct:" + node[1].__name__
        if node[0] == "list":
            return "list[" + " | ".join(sorted(self.key(i) for i in node[1])) + "]"
        return node[0]

    def node(self, depth):
        pool = ["int", "float", "str", "bool", "date", "time", "enum"]
        if depth > 0:
            pool += ["list", "list", "struct", "struct"]
        kind = self.rnd.choice(pool)
        if kind == "enum":
            return ("enum", Enum(self._name("E"), self.rnd.choice([
                {"A": 1, "B": 2}, {"RED": "BLUE", "BLUE": "RED"},
                {"ONLY": ()}, {"A": 1, "B": 2, "ALIAS": 1}])))
        if kind == "struct":
            return ("struct", self.dataclass(depth - 1))
        if kind == "list":
            return ("list", self.slot(depth - 1, none=False))
        return (kind,)

    def slot(self, depth, none=True):
        options, seen = [], set()
        for _ in range(12):
            if len(options) >= self.rnd.choice([1, 1, 2, 2, 3]):
                break
            node = self.node(depth)
            if self.key(node) in seen:
                continue
            seen.add(self.key(node))
            options.append(node)
        if none and self.rnd.random() < 0.25:
            options.append(("none",))
        return tuple(options)

    def annotation(self, slot):
        out = self._hint(slot[0])
        for node in slot[1:]:
            out = out | self._hint(node)
        return out

    def _hint(self, node):
        simple = {"int": int, "float": float, "str": str, "bool": bool,
                  "date": date, "time": time, "none": type(None)}
        if node[0] in simple:
            return simple[node[0]]
        if node[0] in ("enum", "struct"):
            return node[1]
        return list[self.annotation(node[1])]

    def value(self, node):
        if node[0] == "int":
            return self.rnd.choice(_INTS)
        if node[0] == "float":
            return self.rnd.choice(_FLOATS)
        if node[0] == "str":
            return self.rnd.choice(_STRS)
        if node[0] == "bool":
            return self.rnd.choice([True, False])
        if node[0] == "date":
            return self.rnd.choice(_DATES)
        if node[0] == "time":
            return self.rnd.choice(_TIMES)
        if node[0] == "none":
            return None
        if node[0] == "enum":
            return self.rnd.choice(list(node[1]))
        if node[0] == "struct":
            return node[1](**{n: self.value(self.rnd.choice(s))
                              for n, s in self.specs[node[1]]})
        return [self.value(self.rnd.choice(node[1]))
                for _ in range(self.rnd.choice([0, 1, 1, 2, 3]))]

    def _fields(self, slots):
        out = []
        for name, slot in slots:
            served = self.value(self.rnd.choice(slot))
            # a pure recipe: a fresh copy per call, so nothing is shared
            out.append((name, self.annotation(slot),
                        field(default_factory=lambda v=served: copy.deepcopy(v))))
        return out

    def dataclass(self, depth):
        slots = [(f"f{i}", self.slot(depth))
                 for i in range(self.rnd.randint(1, 3))]
        cls = make_dataclass(self._name("S"), self._fields(slots))
        self.specs[cls] = slots
        return cls

    def root(self):
        slots = [(f"f{i}", self.slot(self.rnd.randint(1, 3)))
                 for i in range(self.rnd.randint(1, 4))]
        return make_dataclass(self._name("Root"), self._fields(slots))

    def function(self):
        slots = [(f"f{i}", self.slot(self.rnd.randint(1, 3)))
                 for i in range(self.rnd.randint(1, 4))]
        built = self._fields(slots)
        source = ("def _fn(" + ", ".join(f"{n}=_d{i}" for i, (n, _, _)
                                        in enumerate(built)) + "): pass")
        env = {f"_d{i}": f[2].default_factory() for i, f in enumerate(built)}
        exec(source, env)  # noqa: S102 - the source is generated right here
        fn = env["_fn"]
        fn.__annotations__ = {n: hint for n, hint, _ in built}
        return fn


@settings(max_examples=250, deadline=None,
          suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(min_value=0, max_value=2 ** 24),
        as_function=st.booleans())
def test_generated_defaults_round_trip(seed, as_function):
    factory = _Schemas(random.Random(seed))
    if as_function:
        schema = signature_of(factory.function())
    else:
        schema = struct_of(factory.root())
    round_trip(schema)


@settings(max_examples=150, deadline=None,
          suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(min_value=0, max_value=2 ** 24))
def test_generated_documents_are_portable_and_own_nothing(seed):
    factory = _Schemas(random.Random(seed))
    schema = struct_of(factory.root())
    document = schema.to_dict()
    _assert_portable(document)
    before = json.dumps(document)
    expected = schema.build({})

    other = schema.to_dict()
    _wreck(other)
    assert json.dumps(schema.to_dict()) == before
    _same(expected, schema.build({}))


def _assert_portable(tree, path=()):
    where = ".".join(map(str, path))
    if type(tree) is dict:
        for key, value in tree.items():
            assert type(key) is str, f"{where}: non-str key {key!r}"
            _assert_portable(value, (*path, key))
    elif type(tree) is list:
        for i, value in enumerate(tree):
            _assert_portable(value, (*path, i))
    else:
        assert type(tree) in (str, int, float, bool, type(None)), (
            f"{where}: {type(tree).__name__} is not portable: {tree!r}")


@settings(max_examples=150, deadline=None,
          suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(min_value=0, max_value=2 ** 24))
def test_generated_defaults_share_nothing_between_servings(seed):
    factory = _Schemas(random.Random(seed))
    schema = struct_of(factory.root())
    _assert_disjoint(schema.build({}), schema.build({}))
    written = _document_defaults(schema.to_dict())
    _assert_disjoint(schema.build(schema.decode(written)),
                     schema.build(schema.decode(written)))


def _assert_disjoint(left, right, path=()):
    where = ".".join(map(str, path)) or "<root>"
    if type(left) is not type(right):
        return
    if type(left) is list:
        assert left is not right, f"{where}: one list serves both"
        for i, (a, b) in enumerate(zip(left, right)):
            _assert_disjoint(a, b, (*path, i))
    elif hasattr(left, "__dataclass_fields__"):
        assert left is not right, f"{where}: one instance serves both"
        for f in dc_fields(left):
            _assert_disjoint(getattr(left, f.name), getattr(right, f.name),
                             (*path, f.name))

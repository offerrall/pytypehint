"""Legal-but-unusual Python across the four public entries.

Agent F, release hardening. Every case here is something Python allows and a
schema author can reach: subclasses of builtins, `bool` beside `int`, custom
equality, hostile dict keys, enum aliases and enum values that collide,
dynamically built and homonymous classes, recursion, `frozen`/`slots`/`kw_only`,
gigantic integers, non-finite floats, `-0.0`, and strings Unicode only barely
allows.

Most of them are pinned here because the core already answers them exactly and
the answer is worth keeping. Four were defects when the agent reported them, and
each flipped to a pass when its fix landed.
"""

import json
import math
import time
import unicodedata
from dataclasses import dataclass, field, make_dataclass
from datetime import date, time as dtime
from collections import OrderedDict, defaultdict
from enum import Enum, EnumMeta, IntEnum, StrEnum, auto
from typing import Annotated

import pytest

from pytypehint import (
    Choices, Field, Int, Max, Min, MultipleOf, Pattern, SchemaTypeError,
    SchemaValueError, Step, Struct, signature_of, struct_of,
)


# ---------------------------------------------------------------------------
# Shared schemas
# ---------------------------------------------------------------------------

@dataclass
class Pair:
    s: str
    n: int


@dataclass
class Ints:
    xs: list[int]


@dataclass
class Flag:
    flag: bool


@dataclass
class Num:
    n: int


@dataclass
class Real:
    x: float


@dataclass
class Node:
    n: int
    nxt: "Node | None" = None


@dataclass
class MutualA:
    b: "MutualB | None" = None


@dataclass
class MutualB:
    a: "MutualA | None" = None


class MyStr(str):
    pass


class MyInt(int):
    pass


class MyList(list):
    pass


class MyDict(dict):
    pass


class MyFloat(float):
    pass


# ---------------------------------------------------------------------------
# Subclasses of builtins: exact types, at every entry
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    (MyStr("a"), "expected str, got MyStr"),
    (MyInt(1), "expected str, got MyInt"),
])
def test_a_str_subclass_is_not_a_str(value, expected):
    with pytest.raises(SchemaTypeError) as error:
        struct_of(Pair).resolve({"s": value, "n": 1})

    assert error.value.leaf == expected.replace("MyInt", type(value).__name__)


def test_an_int_subclass_is_not_an_int():
    with pytest.raises(SchemaTypeError) as error:
        struct_of(Pair).resolve({"s": "a", "n": MyInt(1)})

    assert error.value.leaf == "expected int, got MyInt"
    assert error.value.path == ("n",)


def test_a_float_subclass_is_not_a_float():
    with pytest.raises(SchemaTypeError) as error:
        struct_of(Real).resolve({"x": MyFloat(1.5)})

    assert error.value.leaf == "expected float, got MyFloat"


def test_a_list_subclass_is_not_a_list():
    with pytest.raises(SchemaTypeError) as error:
        struct_of(Ints).build({"xs": MyList([1, 2])})

    assert error.value.leaf == "expected list, got MyList"


def test_a_list_of_int_subclasses_is_rejected_per_item():
    with pytest.raises(SchemaTypeError) as error:
        struct_of(Ints).build({"xs": [1, MyInt(2)]})

    assert error.value.path == ("xs", 1)
    assert error.value.leaf == "expected int, got MyInt"


def test_a_dict_subclass_is_not_a_dict_root():
    with pytest.raises(SchemaTypeError) as error:
        struct_of(Pair).build(MyDict(s="a", n=1))

    assert error.value.leaf == "expected dict, got MyDict"


def test_decode_hands_a_dict_subclass_back_untouched():
    # docs/decode.md, "Fresh trees": the promise covers `dict` and `list`
    # exactly, so a subclass is returned as it came and `resolve` reports it.
    schema = struct_of(Pair)
    wire = MyDict(s="a", n=1)

    assert schema.decode(wire) is wire


def test_decode_does_not_descend_into_a_list_subclass():
    wire = MyList([1, 2])

    assert struct_of(Ints).decode({"xs": wire}) == {"xs": wire}
    assert struct_of(Ints).decode({"xs": wire})["xs"] is wire


# ---------------------------------------------------------------------------
# bool is not int, in both directions and at depth
# ---------------------------------------------------------------------------

def test_true_is_not_an_int():
    with pytest.raises(SchemaTypeError) as error:
        struct_of(Num).resolve({"n": True})

    assert error.value.leaf == "expected int, got bool"


def test_one_is_not_a_bool():
    with pytest.raises(SchemaTypeError) as error:
        struct_of(Flag).resolve({"flag": 1})

    assert error.value.leaf == "expected bool, got int"


def test_true_is_not_a_float():
    with pytest.raises(SchemaTypeError) as error:
        struct_of(Real).resolve({"x": True})

    assert error.value.leaf == "expected float, got bool"


def test_true_inside_a_list_of_int_is_rejected():
    with pytest.raises(SchemaTypeError) as error:
        struct_of(Ints).build({"xs": [True]})

    assert error.value.path == ("xs", 0)


def test_decode_does_not_read_a_bool_as_a_float():
    # `Float` reads an int back as a float; `bool` is not that int.
    assert struct_of(Real).decode({"x": True}) == {"x": True}
    assert struct_of(Real).decode({"x": True})["x"] is True


def test_bool_and_int_are_separate_options_of_one_union():
    @dataclass
    class Either:
        v: int | bool

    schema = struct_of(Either)

    assert schema.build({"v": 1}).v == 1
    assert schema.build({"v": True}).v is True


# ---------------------------------------------------------------------------
# dict subclasses that behave: OrderedDict, defaultdict
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("factory, name", [
    (lambda: OrderedDict(s="a", n=1), "OrderedDict"),
    (lambda: defaultdict(int, s="a", n=1), "defaultdict"),
])
def test_a_dict_subclass_root_is_refused_by_resolve(factory, name):
    with pytest.raises(SchemaTypeError) as error:
        struct_of(Pair).resolve(factory())

    assert error.value.leaf == f"expected dict, got {name}"


def test_a_defaultdict_is_never_grown_by_a_failed_resolve():
    # `_resolve_fields` asks `f.name not in data`, which must not be a
    # `__getitem__` that inserts. It refuses the type first, and the mapping
    # comes back with exactly the keys it arrived with.
    data = defaultdict(int)
    data["n"] = 1

    with pytest.raises(SchemaTypeError):
        struct_of(Num).resolve(data)

    assert dict(data) == {"n": 1}


def test_a_nested_ordered_dict_is_reported_as_the_dataclass_it_is_not():
    @dataclass
    class Holder:
        inner: Pair

    with pytest.raises(SchemaTypeError) as error:
        struct_of(Holder).resolve({"inner": OrderedDict(s="a", n=1)})

    assert error.value.leaf == "expected Pair, got OrderedDict"


# ---------------------------------------------------------------------------
# Hostile dict keys
# ---------------------------------------------------------------------------

class _Hostile:
    """Hashes like a reserved key, so any `in dict` probe compares against it."""

    def __init__(self, target: str, log: list):
        self._target = target
        self._log = log

    def __hash__(self):
        return hash(self._target)

    def __eq__(self, other):
        self._log.append(other)
        raise RuntimeError("hostile __eq__ ran")

    def __repr__(self):
        return f"<hostile {self._target!r}>"


@dataclass
class AmbiguousList:
    x: list[str] | list[int]


def test_decode_never_asks_a_non_string_key_whether_it_is_reserved():
    # structure.py `_decode_dict` states the rule: asking would run the key's
    # own `__eq__` on a hash collision, arbitrary code on a path that has to be
    # total. So the subtree is copied and validation reports the keys.
    log: list = []
    key = _Hostile("$value", log)

    decoded = struct_of(AmbiguousList).decode({"x": {key: 1}})

    assert decoded == {"x": {key: 1}}
    assert log == []


def test_resolve_never_runs_user_code_from_a_non_string_key():
    log: list = []

    with pytest.raises(SchemaTypeError) as error:
        struct_of(AmbiguousList).resolve({"x": {_Hostile("$value", log): 1}})

    assert error.value.leaf == "expected string keys, got _Hostile"
    assert log == []


def test_a_single_struct_option_reports_a_non_string_key_cleanly():
    @dataclass
    class Holder:
        inner: Pair

    with pytest.raises(SchemaTypeError) as error:
        struct_of(Holder).resolve({"inner": {"s": "a", "n": 1, 2: 3}})

    assert error.value.path == ("inner",)
    assert error.value.leaf == "expected string keys, got int"


# ---------------------------------------------------------------------------
# Custom __eq__ / __hash__ and expensive comparison
# ---------------------------------------------------------------------------

@dataclass(eq=False)
class Boom:
    n: int

    def __eq__(self, other):
        raise RuntimeError("Boom.__eq__")

    def __hash__(self):
        raise RuntimeError("Boom.__hash__")


def test_a_dataclass_whose_equality_explodes_still_travels_the_pipeline():
    @dataclass
    class Holder:
        b: Boom
        bs: list[Boom] = field(default_factory=list)

    schema = struct_of(Holder)
    built = schema.build({"b": {"n": 1}, "bs": [{"n": 2}]})

    assert type(built.b) is Boom
    assert [type(x) for x in built.bs] == [Boom]
    assert json.loads(json.dumps(schema.to_dict())) == schema.to_dict()


def test_an_instance_default_whose_equality_explodes_certifies_and_is_written():
    @dataclass
    class Holder:
        b: Boom = field(default_factory=lambda: Boom(1))

    schema = struct_of(Holder)
    document = schema.to_dict()

    assert document["defs"]["structs"]["Holder"]["fields"][0]["default"] == {"n": 1}
    assert type(schema.build({}).b) is Boom


def test_the_core_never_compares_or_hashes_a_user_value():
    calls = {"eq": 0, "hash": 0}

    @dataclass(eq=False)
    class Counted:
        n: int

        def __eq__(self, other):
            calls["eq"] += 1
            return isinstance(other, Counted) and other.n == self.n

        def __hash__(self):
            calls["hash"] += 1
            return hash(self.n)

    @dataclass
    class Holder:
        c: Counted = field(default_factory=lambda: Counted(1))

    schema = struct_of(Holder)
    schema.build({})
    schema.build({"c": {"n": 2}})
    schema.to_dict()
    schema.decode({"c": {"n": 2}})

    assert calls == {"eq": 0, "hash": 0}


# ---------------------------------------------------------------------------
# Enums: aliases, colliding values, mutable values, auto, Int/StrEnum
# ---------------------------------------------------------------------------

class Aliased(Enum):
    A = 1
    B = 1      # an alias of A
    C = 2


class Collapsed(Enum):
    A = 1
    B = 1.0    # 1 == 1.0, so an alias of A
    C = True   # True == 1, so an alias of A


class MutableValued(Enum):
    A = [1, 2]
    B = [1, 2]


class Auto(Enum):
    X = auto()
    Y = auto()


class Numbers(IntEnum):
    ONE = 1


class Letters(StrEnum):
    A = "a"


def test_an_enum_alias_resolves_to_the_member_it_aliases():
    @dataclass
    class Holder:
        e: Aliased = Aliased.B

    schema = struct_of(Holder)
    document = schema.to_dict()

    assert schema.fields[0].default is Aliased.A
    assert document["defs"]["enums"]["Aliased"]["members"] == ["A", "C"]
    assert document["defs"]["structs"]["Holder"]["fields"][0]["default"] == "A"


def test_decode_accepts_an_alias_name_and_returns_the_canonical_member():
    @dataclass
    class Holder:
        e: Aliased

    schema = struct_of(Holder)

    assert schema.decode({"e": "B"})["e"] is Aliased.A
    assert schema.build(schema.decode({"e": "B"})).e is Aliased.A


def test_members_with_equal_values_collapse_and_the_document_says_so():
    @dataclass
    class Holder:
        e: Collapsed = Collapsed.C

    document = struct_of(Holder).to_dict()

    assert document["defs"]["enums"]["Collapsed"]["members"] == ["A"]
    assert document["defs"]["structs"]["Holder"]["fields"][0]["default"] == "A"


def test_a_mutable_enum_value_never_reaches_the_document():
    @dataclass
    class Holder:
        e: MutableValued = MutableValued.A

    schema = struct_of(Holder)
    before = schema.to_dict()
    MutableValued.A.value.append(99)

    assert schema.to_dict() == before
    assert schema.to_dict()["defs"]["enums"]["MutableValued"]["members"] == ["A"]
    assert schema.build({}).e is MutableValued.A


def test_auto_int_enum_and_str_enum_all_travel_by_member_name():
    @dataclass
    class Holder:
        a: Auto
        i: Numbers
        s: Letters

    schema = struct_of(Holder)
    wire = {"a": "X", "i": "ONE", "s": "A"}

    assert schema.build(schema.decode(wire)) == Holder(Auto.X, Numbers.ONE, Letters.A)


def test_an_int_enum_member_is_not_an_int_and_a_str_enum_member_is_not_a_str():
    with pytest.raises(SchemaTypeError) as int_error:
        struct_of(Num).resolve({"n": Numbers.ONE})
    with pytest.raises(SchemaTypeError) as str_error:
        struct_of(Pair).resolve({"s": Letters.A, "n": 1})

    assert int_error.value.leaf == "expected int, got Numbers"
    assert str_error.value.leaf == "expected str, got Letters"


def test_an_int_enum_beside_an_int_routes_by_exact_type():
    @dataclass
    class Holder:
        v: int | Numbers

    schema = struct_of(Holder)

    assert schema.build({"v": 5}).v == 5
    assert schema.build({"v": Numbers.ONE}).v is Numbers.ONE
    # `int` and an `IntEnum` share no portable spelling: the enum travels as a
    # name, the int as a number, so a bare number is unambiguous.
    assert schema.decode({"v": 5}) == {"v": 5}


def test_a_str_enum_beside_a_str_needs_the_portable_wrapper():
    @dataclass
    class Holder:
        v: str | Letters

    schema = struct_of(Holder)

    assert schema.decode({"v": "A"}) == {"v": "A"}
    assert schema.decode({"v": {"$type": "Letters", "$value": "A"}})["v"] is Letters.A


def test_a_member_name_that_is_not_an_identifier_round_trips():
    # The functional API admits any string as a member name, and `$type` is the
    # most hostile one available. It is a value on the wire, never a key, so it
    # cannot collide with the discriminator.
    Weird = Enum("Weird", {"$type": 1, "ok": 2})

    @dataclass
    class Holder:
        w: Weird = Weird["$type"]

    schema = struct_of(Holder)
    document = schema.to_dict()

    assert document["defs"]["enums"]["Weird"]["members"] == ["$type", "ok"]
    assert document["defs"]["structs"]["Holder"]["fields"][0]["default"] == "$type"
    assert schema.decode({"w": "$type"})["w"] is Weird["$type"]


def test_decode_leaves_an_unknown_enum_name_alone():
    @dataclass
    class Holder:
        e: Aliased

    assert struct_of(Holder).decode({"e": "NOPE"}) == {"e": "NOPE"}


# ---------------------------------------------------------------------------
# Dynamically created and homonymous classes
# ---------------------------------------------------------------------------

def _target():
    return make_dataclass("Target", [("n", int)])


def test_two_classes_with_one_name_and_qualname_get_distinct_document_ids():
    first, second = _target(), _target()

    @dataclass
    class Holder:
        a: first
        b: second

    schema = struct_of(Holder)
    document = schema.to_dict()
    structs = document["defs"]["structs"]

    assert first.__qualname__ == second.__qualname__
    assert list(structs) == ["Holder", "Target", "Target#2"]
    assert [structs[i]["name"] for i in structs] == ["Holder", "Target", "Target"]
    assert type(schema.build({"a": {"n": 1}, "b": {"n": 2}})) is Holder


def test_two_classes_with_one_name_cannot_be_options_of_one_field():
    first, second = _target(), _target()

    @dataclass
    class Holder:
        x: first | second

    with pytest.raises(ValueError, match="duplicate discriminator name"):
        struct_of(Holder)


def test_a_class_actually_named_like_a_generated_id_does_not_collide():
    first, second = _target(), _target()
    shadow = make_dataclass("Target#2", [("n", int)])

    @dataclass
    class Holder:
        a: first
        b: second
        c: shadow

    structs = struct_of(Holder).to_dict()["defs"]["structs"]

    assert list(structs) == ["Holder", "Target", "Target#2", "Target#2#2"]
    assert structs["Target#2"]["name"] == "Target"
    assert structs["Target#2#2"]["name"] == "Target#2"
    assert len(set(structs)) == len(structs)


def test_two_homonymous_enums_are_separate_definitions_but_never_one_field():
    first = Enum("Role", {"A": 1})
    second = Enum("Role", {"B": 2})

    @dataclass
    class Holder:
        a: first
        b: second

    @dataclass
    class OneField:
        x: first | second

    enums = struct_of(Holder).to_dict()["defs"]["enums"]

    assert list(enums) == ["Role", "Role#2"]
    assert [enums[i]["name"] for i in enums] == ["Role", "Role"]
    with pytest.raises(ValueError, match="duplicate discriminator name"):
        struct_of(OneField)


def test_a_dataclass_and_an_enum_sharing_a_class_name_coexist_in_one_field():
    # restrictions.md: two discriminators, two namespaces, so this pair stays
    # admissible. Both spellings must still route.
    Shaped = make_dataclass("Same", [("n", int)])
    Named = Enum("Same", {"A": 1})

    @dataclass
    class Holder:
        x: Shaped | Named

    schema = struct_of(Holder)

    assert type(schema.build({"x": {"n": 1}}).x) is Shaped
    assert schema.build({"x": Named.A}).x is Named.A
    assert schema.decode({"x": "A"})["x"] is Named.A
    assert json.loads(json.dumps(schema.to_dict())) == schema.to_dict()


@pytest.mark.parametrize("name", ["with space", "$type", "", "\U0001f600"])
def test_a_class_name_that_is_not_an_identifier_is_carried_verbatim(name):
    cls = dataclass(type(name, (), {"__annotations__": {"n": int}}))

    document = struct_of(cls).to_dict()

    assert document["defs"]["structs"][document["root"]]["name"] == name
    assert json.loads(json.dumps(document)) == document


# ---------------------------------------------------------------------------
# Dataclasses defined inside functions
# ---------------------------------------------------------------------------

def test_a_local_dataclass_without_forward_references_compiles():
    @dataclass
    class Local:
        n: int

    assert struct_of(Local).build({"n": 1}).n == 1


@pytest.mark.parametrize("build", ["self", "sibling"])
def test_a_local_dataclass_with_a_forward_reference_cannot_be_read(build):
    # Not pytypehint's rule: `get_type_hints` resolves a string annotation in
    # module globals, and a class defined in a function body is not there. The
    # NameError is pinned so a change in either direction is noticed, and the
    # restriction is reported as undocumented.
    if build == "self":
        @dataclass
        class Local:
            nxt: "Local | None" = None
        target = Local
    else:
        @dataclass
        class Inner:
            n: int

        @dataclass
        class Outer:
            i: "Inner"
        target = Outer

    with pytest.raises(NameError):
        struct_of(target)


# ---------------------------------------------------------------------------
# Recursion and mutual recursion
# ---------------------------------------------------------------------------

def test_a_recursive_field_reuses_the_root_struct_object():
    schema = struct_of(Node)

    assert schema.fields[1].shape[0] is schema


def test_mutual_recursion_closes_the_loop_on_the_root():
    schema = struct_of(MutualA)
    inner_b = schema.fields[0].shape[0]

    assert type(inner_b) is Struct
    assert inner_b.fields[0].shape[0] is schema


def test_a_recursive_document_terminates_and_points_back():
    document = struct_of(Node).to_dict()
    nxt = document["defs"]["structs"]["Node"]["fields"][1]["shape"]

    assert document["root"] == "Node"
    assert {node.get("ref") for node in nxt} == {"Node", None}
    assert json.loads(json.dumps(document)) == document


def test_recursion_builds_and_decodes_at_depth():
    schema = struct_of(Node)
    wire = {"n": 1, "nxt": {"n": 2, "nxt": {"n": 3}}}

    assert schema.build(schema.decode(wire)) == Node(1, Node(2, Node(3)))
    assert struct_of(MutualA).build({"b": {"a": {"b": None}}}) == MutualA(MutualB(MutualA()))


# ---------------------------------------------------------------------------
# frozen / slots / kw_only / inheritance
# ---------------------------------------------------------------------------

def test_inheritance_keeps_the_base_fields_first():
    @dataclass
    class Base:
        a: int

    @dataclass
    class Child(Base):
        b: str

    schema = struct_of(Child)

    assert [f.name for f in schema.fields] == ["a", "b"]
    assert schema.build({"a": 1, "b": "x"}) == Child(1, "x")


def test_frozen_slots_and_kw_only_all_compile_and_build():
    @dataclass(frozen=True)
    class Frozen:
        a: int

    @dataclass(slots=True)
    class Slotted:
        a: int

    @dataclass(kw_only=True)
    class KwOnly:
        a: int
        b: str = "z"

    @dataclass
    class PerField:
        a: int
        b: str = field(kw_only=True, default="z")

    @dataclass(frozen=True, slots=True, kw_only=True)
    class All3:
        a: int = 1

    assert struct_of(Frozen).build({"a": 1}) == Frozen(1)
    assert struct_of(Slotted).build({"a": 1}) == Slotted(1)
    assert struct_of(KwOnly).build({"a": 1}) == KwOnly(a=1, b="z")
    assert struct_of(PerField).build({"a": 1}) == PerField(1, b="z")
    assert struct_of(All3).build({}) == All3(a=1)


def test_a_slotted_dataclass_recurses_like_any_other():
    @dataclass(slots=True)
    class SlottedNode:
        a: int
        nxt: "SlottedNode | None" = None

    # A forward reference to a module-level name; `slots=True` rebuilds the
    # class, so the reference must resolve to the rebuilt one.
    SlottedNode.__module__ = __name__
    globals()["SlottedNode"] = SlottedNode
    try:
        schema = struct_of(SlottedNode)
        assert schema.build({"a": 1, "nxt": {"a": 2}}).nxt.a == 2
    finally:
        del globals()["SlottedNode"]


# ---------------------------------------------------------------------------
# Depth and cycles: RecursionError, as restrictions.md documents
# ---------------------------------------------------------------------------

def _chain(depth: int) -> dict:
    root: dict = {"n": 0}
    cursor = root
    for i in range(depth):
        cursor["nxt"] = {"n": i}
        cursor = cursor["nxt"]
    return root


@pytest.mark.parametrize("operation", ["decode", "resolve", "build"])
def test_very_deep_data_raises_recursion_error(operation):
    schema = struct_of(Node)

    with pytest.raises(RecursionError):
        getattr(schema, operation)(_chain(3000))


@pytest.mark.parametrize("operation", ["decode", "resolve", "build"])
def test_a_cyclic_dict_raises_recursion_error(operation):
    schema = struct_of(Node)
    cycle: dict = {"n": 1}
    cycle["nxt"] = cycle

    with pytest.raises(RecursionError):
        getattr(schema, operation)(cycle)


@pytest.mark.parametrize("operation", ["decode", "build"])
def test_a_cyclic_list_raises_recursion_error(operation):
    @dataclass
    class Listy:
        xs: list["Listy | None"] = field(default_factory=list)

    Listy.__module__ = __name__
    globals()["Listy"] = Listy
    try:
        schema = struct_of(Listy)
        cycle: dict = {"xs": []}
        cycle["xs"].append(cycle)

        with pytest.raises(RecursionError):
            getattr(schema, operation)(cycle)
    finally:
        del globals()["Listy"]


# ---------------------------------------------------------------------------
# Nothing is mutated, nothing is aliased
# ---------------------------------------------------------------------------

@dataclass
class Served:
    a: int
    b: int = 5
    xs: list[int] = field(default_factory=lambda: [1])


def test_resolve_and_build_leave_the_input_untouched():
    schema = struct_of(Served)
    for operation in (schema.resolve, schema.build):
        data = {"a": 1}
        operation(data)
        assert data == {"a": 1}


def test_a_default_container_is_fresh_per_serving_and_never_shared():
    schema = struct_of(Served)
    first, second = schema.build({"a": 1}), schema.build({"a": 1})

    assert first.xs is not second.xs
    first.xs.append(99)
    assert schema.build({"a": 1}).xs == [1]


def test_build_rebuilds_a_supplied_list_instead_of_aliasing_it():
    schema = struct_of(Served)
    mine = [7]

    built = schema.build({"a": 1, "xs": mine})

    assert built.xs == [7]
    assert built.xs is not mine
    built.xs.append(8)
    assert mine == [7]


# ---------------------------------------------------------------------------
# Gigantic integers
# ---------------------------------------------------------------------------

_HUGE = 10 ** 5000


def test_an_accepted_gigantic_int_survives_the_whole_pipeline():
    @dataclass
    class Holder:
        n: int = _HUGE

    schema = struct_of(Holder)
    document = schema.to_dict()

    assert schema.build({}).n == _HUGE
    assert schema.build({"n": _HUGE + 1}).n == _HUGE + 1
    # The document holds the exact integer; turning it into JSON text is the
    # caller's side of the boundary, and CPython's int_max_str_digits limit
    # lives there (reported, not asserted here).
    assert document["defs"]["structs"]["Holder"]["fields"][0]["default"] == _HUGE


@pytest.mark.parametrize("hint, value, leaf", [
    pytest.param(Annotated[int, Max(10)], _HUGE, "too large", id="max"),
    pytest.param(Annotated[int, MultipleOf(3)], _HUGE + 1,
                 "not a multiple of 3", id="multiple_of"),
    pytest.param(Annotated[int, Choices(values=(1,))], _HUGE,
                 "not a choice", id="choices"),
])
def test_an_int_violation_reports_the_violation_not_the_digit_limit(hint, value, leaf):
    schema = struct_of(make_dataclass("Bounded", [("n", hint)]))

    with pytest.raises(SchemaValueError) as error:
        schema.resolve({"n": value})

    assert "Exceeds the limit" not in error.value.leaf
    assert error.value.leaf.startswith(leaf)


def test_a_float_bound_beyond_the_float_range_fails_as_a_schema_error():
    with pytest.raises((TypeError, ValueError)):
        struct_of(make_dataclass("Holder", [("x", Annotated[float, Min(10 ** 400)])]))


# ---------------------------------------------------------------------------
# Non-finite floats and -0.0
# ---------------------------------------------------------------------------

def test_non_finite_values_and_bounds_are_refused():
    schema = struct_of(Real)
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(SchemaValueError, match="not finite"):
            schema.resolve({"x": bad})
        with pytest.raises(ValueError, match="must be finite"):
            struct_of(make_dataclass("H", [("x", Annotated[float, Min(bad)])]))


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_a_non_finite_step_is_refused(bad):
    with pytest.raises(ValueError):
        Step(bad)


def test_a_non_finite_step_would_break_the_document_if_it_got_through():
    # The consequence of F-03, pinned so the fix can be seen to remove it. Once
    # `Step` refuses nan this raises before the document exists, and the test
    # still passes -- either way a NaN never reaches a strict JSON writer.
    try:
        schema = struct_of(make_dataclass(
            "H", [("x", Annotated[float, Step(float("nan"))])]))
    except ValueError:
        return

    document = schema.to_dict()
    with pytest.raises(ValueError, match="not JSON compliant"):
        json.dumps(document, allow_nan=False)


def test_minus_zero_keeps_its_sign_through_the_whole_pipeline():
    @dataclass
    class Holder:
        x: float = -0.0

    schema = struct_of(Holder)
    written = schema.to_dict()["defs"]["structs"]["Holder"]["fields"][0]["default"]

    assert math.copysign(1.0, schema.resolve({"x": -0.0})["x"]) == -1.0
    assert math.copysign(1.0, schema.build({}).x) == -1.0
    assert math.copysign(1.0, written) == -1.0
    assert math.copysign(1.0, json.loads(json.dumps(written))) == -1.0


def test_minus_zero_satisfies_a_zero_choice_and_not_an_exclusive_zero_bound():
    @dataclass
    class Chosen:
        x: Annotated[float, Choices(values=(0.0,))] = -0.0

    assert math.copysign(1.0, struct_of(Chosen).build({}).x) == -1.0

    with pytest.raises(SchemaValueError, match="too small"):
        struct_of(make_dataclass(
            "H", [("x", Annotated[float, Min(0.0, exclusive=True)], field(default=-0.0))]))


def test_zero_and_minus_zero_are_the_same_choice():
    with pytest.raises(ValueError, match="must not repeat"):
        Choices(values=(0.0, -0.0))


# ---------------------------------------------------------------------------
# Unicode
# ---------------------------------------------------------------------------

def test_a_non_ascii_identifier_is_a_field_name_like_any_other():
    name = "café"
    cls = dataclass(type("Holder", (), {"__annotations__": {name: int}}))

    schema = struct_of(cls)
    document = schema.to_dict()

    assert schema.resolve({name: 1}) == {name: 1}
    assert document["defs"]["structs"]["Holder"]["fields"][0]["name"] == name
    assert json.loads(json.dumps(document)) == document


def test_a_field_name_only_a_normalizing_reader_would_confuse():
    # NFC and NFD spellings of one word are two distinct identifiers. Python's
    # own `@dataclass` cannot build the pair (its generated __init__ is compiled
    # from source, and identifiers there are NFKC-normalized), but the
    # hand-built `Struct`/`Field` surface can, so the document can carry two
    # names a reader that normalizes would collapse into one.
    nfc, nfd = "café", "café"
    assert nfc != nfd and unicodedata.normalize("NFC", nfd) == nfc

    class Holder:
        pass

    document = Struct(cls=Holder, fields=(Field(name=nfc, shape=(Int(),)),
                                          Field(name=nfd, shape=(Int(),)))).to_dict()
    names = [f["name"] for f in document["defs"]["structs"]["Holder"]["fields"]]

    assert names == [nfc, nfd]
    assert len({unicodedata.normalize("NFC", n) for n in names}) == 1


@pytest.mark.parametrize("name", ["a​b", "١٢", "emoji\U0001f600"])
def test_a_zero_width_or_non_xid_field_name_is_not_an_identifier(name):
    assert not name.isidentifier()
    with pytest.raises(ValueError, match="must be an identifier"):
        Field(name=name, shape=(Int(),))


@pytest.mark.parametrize("value", [
    "\U0001f600",              # astral plane
    "áb",                # combining acute
    "‮abc"[:3],           # RTL override, truncated to three code points
    "\ud800",                  # a lone surrogate: legal in a Python str
    "\U0001f1e6\U0001f1e7",    # regional indicators, one flag, two code points
])
def test_string_limits_count_code_points_not_graphemes(value):
    schema = struct_of(make_dataclass(
        "H", [("s", Annotated[str, Min(1), Max(3)])]))

    assert schema.resolve({"s": value}) == {"s": value}


def test_a_grapheme_cluster_is_several_code_points_to_max():
    schema = struct_of(make_dataclass("H", [("s", Annotated[str, Max(1)])]))
    family = "\U0001f468‍\U0001f469‍\U0001f467"

    assert schema.resolve({"s": "\U0001f600"}) == {"s": "\U0001f600"}
    for many in (family, "é"):
        with pytest.raises(SchemaValueError, match="too long"):
            schema.resolve({"s": many})


def test_a_pattern_does_not_treat_every_unicode_digit_as_a_digit_by_accident():
    # `re` without re.ASCII matches Arabic-Indic digits with \d. The core
    # compiles the author's pattern verbatim, so this is the author's choice and
    # is pinned as such.
    schema = struct_of(make_dataclass("H", [("s", Annotated[str, Pattern(r"\d+")])]))

    assert schema.resolve({"s": "١٢"}) == {"s": "١٢"}


def test_a_lone_surrogate_default_survives_the_document_but_not_utf_8():
    schema = struct_of(dataclass(
        type("H", (), {"__annotations__": {"s": str}, "s": "\ud800"})))
    document = schema.to_dict()

    assert json.loads(json.dumps(document)) == document
    with pytest.raises(UnicodeEncodeError):
        json.dumps(document, ensure_ascii=False).encode("utf-8")


# ---------------------------------------------------------------------------
# The portable round trip, over every awkward default at once
# ---------------------------------------------------------------------------

class RoundTrip(Enum):
    A = 1
    B = 1


@dataclass
class Awkward:
    negative_zero: float = -0.0
    whole: float = 3.0
    aliased: RoundTrip = RoundTrip.B
    day: date = date(2026, 8, 8)
    at: dtime = dtime(14, 30)
    number: int | float = 10
    when: str | date = date(2026, 1, 1)
    mixed: list[str | date] = field(
        default_factory=lambda: [date(2026, 1, 1), "x"])
    big: int = 10 ** 40
    text: str = "café \U0001f600 ‮RTL"


def test_every_awkward_default_round_trips_through_json_decode_and_build():
    schema = struct_of(Awkward)
    document = json.loads(json.dumps(schema.to_dict()))
    defaults = {f["name"]: f["default"]
                for f in document["defs"]["structs"]["Awkward"]["fields"]}

    rebuilt = schema.build(schema.decode(defaults))

    assert rebuilt == schema.build({}) == Awkward()
    assert math.copysign(1.0, rebuilt.negative_zero) == -1.0
    assert rebuilt.aliased is RoundTrip.A
    assert type(rebuilt.whole) is float


def test_two_documents_from_one_definition_are_byte_identical():
    assert json.dumps(struct_of(Awkward).to_dict()) == json.dumps(struct_of(Awkward).to_dict())


# ---------------------------------------------------------------------------
# signature_of, with functions Python allows but nobody writes
# ---------------------------------------------------------------------------

def test_a_lambda_with_a_real_name_is_accepted_and_a_bare_one_is_not():
    named = lambda x: x       # noqa: E731
    named.__name__ = "renamed"
    named.__annotations__ = {"x": int}

    assert signature_of(named).name == "renamed"
    with pytest.raises(TypeError, match="lambdas have no usable name"):
        signature_of(lambda x: x)


@pytest.mark.parametrize("name", ["not an identifier", "$type", ""])
def test_a_function_whose_name_is_not_an_identifier_is_refused(name):
    def target(x: int):
        pass

    target.__name__ = name

    with pytest.raises(ValueError, match="must be an identifier"):
        signature_of(target)


def test_a_non_string_docstring_is_refused():
    def target(x: int):
        pass

    target.__doc__ = 12345  # type: ignore[assignment]

    with pytest.raises(TypeError, match="Signature.doc must be str or None"):
        signature_of(target)


def test_functools_wraps_describes_the_wrapped_function_not_the_wrapper():
    import functools

    def target(a: int, b: str = "z"):
        """target doc"""

    @functools.wraps(target)
    def wrapper(extra: float, **kwargs):
        return target(**kwargs)

    schema = signature_of(wrapper)

    # `inspect.signature` follows `__wrapped__` and `wraps` copies
    # `__annotations__`, so both halves agree on `target` and neither mentions
    # `extra`. Standard Python semantics, pinned because it is surprising.
    assert [p.name for p in schema.params] == ["a", "b"]
    assert schema.doc == "target doc"
    assert schema.build({"a": 1}) == {"a": 1, "b": "z"}


def test_generator_and_async_functions_are_plain_functions_to_the_compiler():
    def generator(x: int):
        yield x

    async def coroutine(x: int):
        pass

    assert signature_of(generator).build({"x": 1}) == {"x": 1}
    assert signature_of(coroutine).build({"x": 1}) == {"x": 1}


def test_a_keyword_only_signature_builds_and_a_positional_only_one_does_not():
    def kw_only(*, a: int, b: int = 2):
        pass

    def pos_only(a: int, /, b: int = 1):
        pass

    assert signature_of(kw_only).build({"a": 1}) == {"a": 1, "b": 2}
    with pytest.raises(TypeError, match="positional-only"):
        signature_of(pos_only)


# ---------------------------------------------------------------------------
# Hand-built shapes, and the enum the core has to trust
# ---------------------------------------------------------------------------

def test_a_hand_built_struct_over_a_plain_class_constructs_through_it():
    class Holder:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    schema = Struct(cls=Holder, fields=(Field(name="n", shape=(Int(),)),))

    assert type(schema.build({"n": 1})) is Holder
    assert schema.to_dict()["defs"]["structs"]["Holder"]["name"] == "Holder"


def test_decode_trusts_the_enum_class_for_a_member_lookup():
    # `_decode_shape` guards only KeyError around `shape.cls[value]`, which is
    # exactly what `EnumMeta` raises. A metaclass that raises something else
    # propagates -- pinned so the trust boundary is visible rather than assumed.
    class Angry(EnumMeta):
        def __getitem__(cls, name):
            raise RuntimeError("angry __getitem__")

    class Hostile(Enum, metaclass=Angry):
        A = 1

    schema = struct_of(make_dataclass("H", [("e", Hostile)]))

    assert schema.resolve({"e": Hostile.A}) == {"e": Hostile.A}
    assert json.loads(json.dumps(schema.to_dict())) == schema.to_dict()
    with pytest.raises(RuntimeError):
        schema.decode({"e": "A"})


# ---------------------------------------------------------------------------
# Cost: none of this is quadratic or exponential
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_a_shared_dataclass_is_referenced_not_inlined():
    # Each level reuses the level below twice: inlining would be 2**n nodes.
    current = make_dataclass("D0", [("v", int)])
    for i in range(1, 18):
        current = make_dataclass(f"D{i}", [("a", current), ("b", current)])

    started = time.perf_counter()
    document = struct_of(current).to_dict()
    elapsed = time.perf_counter() - started

    assert len(document["defs"]["structs"]) == 18
    assert elapsed < 5.0


@pytest.mark.slow
def test_a_very_long_string_is_measured_not_walked():
    schema = struct_of(make_dataclass(
        "H", [("s", Annotated[str, Max(10), Pattern("[a-z]*")])]))
    huge = "x" * 2_000_000

    started = time.perf_counter()
    with pytest.raises(SchemaValueError, match="too long"):
        schema.resolve({"s": huge})
    elapsed = time.perf_counter() - started

    # The length bound is checked before the pattern, so nothing scans 2 MB.
    assert elapsed < 1.0

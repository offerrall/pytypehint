"""Second adversarial round on the atom/error/routing hardening.

Five claims were made and are attacked here:

A. `utils.render_number` keeps a schema error reportable when a value is too
   large for CPython to spell (`sys.get_int_max_str_digits`).
B. `shapes._finite` keeps every atom rejection inside TypeError/ValueError.
C. `atoms.Step` keeps NaN/Infinity out of an accepted schema's document.
D. `structure._data_shape` never probes a reserved key before the keys are typed,
   so routing runs no user `__eq__`.
E. `errors._renote` carries PEP 678 notes across a rebuild.

All five hold now. The three that did not — every length-shaped message still
interpolating a raw int, the key guard that ran only where there was a wrapper to
find, and the sibling re-raises that dropped their notes — were pinned here as
strict failures until each fix landed, and are plain tests from here on.
"""

import json
import math
import pickle
from dataclasses import dataclass, field, make_dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Annotated

import pytest
from hypothesis import given, seed, settings, strategies as st

from pytypehint import (
    Choices, Field, FileHint, Float, Int, List, Max, Min, MultipleOf, Rows,
    SchemaTypeError, SchemaValueError, Slider, Step, Str, Struct, struct_of,
    signature_of,
)
from pytypehint.utils import render_number
from pytypehint.validation import check_options_value

# 5001 digits: past the 4300-digit default of `sys.get_int_max_str_digits()`, so
# `str()` of it raises without any interpreter setting being touched. Mutating
# that limit is process-global and would leak into every other test.
_HUGE = 10 ** 5000
_LIMIT = "Exceeds the limit"


# ---------------------------------------------------------------------------
# A — render_number: the spelling of ordinary messages must not move
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    (0, "0"),
    (-1, "-1"),
    (2 ** 53 + 1, "9007199254740993"),
    (1.5, "1.5"),
    (-0.0, "-0.0"),
    (float("inf"), "inf"),
    ((), "()"),
    ((1,), "(1,)"),
    ((1, 2), "(1, 2)"),
    (("a",), "('a',)"),
])
def test_render_number_is_str_for_everything_str_can_spell(value, expected):
    assert render_number(value) == expected
    assert render_number(value) == str(value)


@pytest.mark.parametrize("shape, value, message", [
    (Int(min=Min(0)), -1, "too small: -1, minimum 0"),
    (Int(min=Min(0, exclusive=True)), 0, "too small: 0, minimum 0 (exclusive)"),
    (Int(max=Max(100)), 145, "too large: 145, maximum 100"),
    (Int(max=Max(1, exclusive=True)), 1, "too large: 1, maximum 1 (exclusive)"),
    (Int(multiple_of=MultipleOf(3)), 4, "not a multiple of 3: 4"),
    (Int(choices=Choices(values=(1,))), 2, "not a choice: 2, expected one of (1,)"),
    (Int(choices=Choices(values=(1, 2))), 3,
     "not a choice: 3, expected one of (1, 2)"),
])
def test_ordinary_int_messages_are_spelled_character_for_character(
        shape, value, message):
    with pytest.raises(SchemaValueError) as error:
        shape._check(value)

    assert error.value.leaf == message
    assert str(error.value) == message


def test_a_single_gigantic_choice_keeps_the_trailing_comma_of_its_tuple():
    with pytest.raises(SchemaValueError) as error:
        Int(choices=Choices(values=(_HUGE,)))._check(1)

    assert error.value.leaf == (
        f"not a choice: 1, expected one of (<int of {_HUGE.bit_length()} bits>,)")


def test_a_mixed_choices_tuple_renders_only_the_unspellable_members():
    with pytest.raises(SchemaValueError) as error:
        Int(choices=Choices(values=(1, _HUGE)))._check(2)

    assert error.value.leaf == (
        f"not a choice: 2, expected one of (1, <int of {_HUGE.bit_length()} bits>)")


@pytest.mark.parametrize("shape, value", [
    (Int(min=Min(_HUGE)), 0),
    (Int(max=Max(-_HUGE)), 0),
    (Int(multiple_of=MultipleOf(_HUGE)), 1),
    (Int(choices=Choices(values=(_HUGE,))), 1),
])
def test_an_int_violation_never_reports_the_digit_limit(shape, value):
    with pytest.raises(SchemaValueError) as error:
        shape._check(value)

    assert _LIMIT not in error.value.leaf


@pytest.mark.parametrize("build", [
    pytest.param(lambda: Int(min=Min(_HUGE), max=Max(-_HUGE)), id="empty-range"),
    pytest.param(lambda: Int(min=Min(_HUGE), choices=Choices(values=(1,))),
                 id="choice-below-min"),
    pytest.param(lambda: Int(max=Max(-_HUGE), choices=Choices(values=(1,))),
                 id="choice-above-max"),
    pytest.param(
        lambda: Int(multiple_of=MultipleOf(_HUGE), choices=Choices(values=(1,))),
        id="choice-not-a-multiple"),
    pytest.param(
        lambda: Int(min=Min(1), max=Max(2), multiple_of=MultipleOf(_HUGE)),
        id="no-multiple-in-range"),
    pytest.param(lambda: Float(min=Min(_HUGE)), id="float-min-out-of-range"),
    pytest.param(lambda: Float(max=Max(-_HUGE)), id="float-max-out-of-range"),
    pytest.param(lambda: Float(step=Step(_HUGE)), id="float-step-out-of-range"),
    pytest.param(lambda: Step(-_HUGE), id="step-not-positive"),
])
def test_a_construction_rejection_never_reports_the_digit_limit(build):
    with pytest.raises((TypeError, ValueError)) as error:
        build()

    assert _LIMIT not in str(error.value)


# ---------------------------------------------------------------------------
# A — the surfaces that were left out (defects)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hint, value, leaf", [
    pytest.param(Annotated[str, Min(_HUGE)], "a", "too short", id="str-too-short"),
    pytest.param(Annotated[list[int], Min(_HUGE)], [], "too few items",
                 id="list-too-few"),
])
def test_a_length_violation_reports_the_violation_not_the_digit_limit(
        hint, value, leaf):
    schema = struct_of(make_dataclass("Bounded", [("v", hint)]))

    with pytest.raises(SchemaValueError) as error:
        schema.resolve({"v": value})

    assert error.value.path == ("v",)
    assert _LIMIT not in error.value.leaf
    assert error.value.leaf.startswith(leaf)


def test_a_length_violation_keeps_its_coordinates_at_depth():
    inner = make_dataclass("Inner", [("s", Annotated[str, Min(_HUGE)])])
    schema = struct_of(make_dataclass("Outer", [("inner", inner)]))

    with pytest.raises(SchemaValueError) as error:
        schema.resolve({"inner": {"s": "a"}})

    assert error.value.path == ("inner", "s")
    assert _LIMIT not in error.value.leaf


def test_a_length_violation_survives_signature_resolve():
    def handler(s: Annotated[str, Min(_HUGE)]) -> None:
        """Bounded past what CPython will spell."""

    with pytest.raises(SchemaValueError) as error:
        signature_of(handler).resolve({"s": "a"})

    assert _LIMIT not in error.value.leaf


def test_certification_of_a_length_bounded_default_stays_structured():
    holder = make_dataclass(
        "Holder", [("s", Annotated[str, Min(_HUGE)], field(default="a"))])

    with pytest.raises(SchemaValueError) as error:
        struct_of(holder)

    assert error.value.path == ("s", "default")
    assert _LIMIT not in error.value.leaf


@pytest.mark.parametrize("build, fragment", [
    pytest.param(lambda: MultipleOf(-_HUGE), "must be > 0", id="multiple-of"),
    pytest.param(lambda: Rows(-_HUGE), "must be > 0", id="rows"),
    pytest.param(lambda: FileHint(min_size=-_HUGE), "must be >= 0",
                 id="file-hint-min-size"),
    pytest.param(lambda: FileHint(min_size=_HUGE, max_size=1), "exceeds max_size",
                 id="file-hint-min-exceeds-max"),
    pytest.param(lambda: Str(min=Min(-_HUGE)), "must be >= 0", id="str-min"),
    pytest.param(lambda: Str(max=Max(-_HUGE)), "must be >= 0", id="str-max"),
    pytest.param(lambda: Str(min=Min(_HUGE), max=Max(1)), "empty range",
                 id="str-empty-range"),
    pytest.param(lambda: Str(min=Min(_HUGE), choices=Choices(values=("a",))),
                 "shorter than minimum", id="str-choice-too-short"),
    pytest.param(lambda: List(item=(Int(),), min=Min(-_HUGE)), "must be >= 0",
                 id="list-min"),
    pytest.param(lambda: List(item=(Int(),), max=Max(-_HUGE)), "must be >= 0",
                 id="list-max"),
    pytest.param(lambda: List(item=(Int(),), min=Min(_HUGE), max=Max(1)),
                 "empty range", id="list-empty-range"),
])
def test_an_atom_or_length_rejection_states_its_own_rule(build, fragment):
    with pytest.raises((TypeError, ValueError)) as error:
        build()

    assert _LIMIT not in str(error.value)
    assert fragment in str(error.value)


def test_matches_no_option_notes_state_why_each_option_declined():
    shapes = (List(item=(Str(min=Min(_HUGE)),)), List(item=(Int(),)))

    with pytest.raises(SchemaValueError) as error:
        check_options_value(shapes, ["a"])

    assert all(_LIMIT not in note for note in error.value.__notes__)


# ---------------------------------------------------------------------------
# B — every atom rejection stays inside TypeError/ValueError
# ---------------------------------------------------------------------------

class _MyInt(int):
    pass


class _MyFloat(float):
    pass


class _Indexy:
    def __index__(self):
        return 3


class _Floaty:
    def __float__(self):
        return 3.0


_HOSTILE_NUMBERS = [
    float("nan"), float("inf"), float("-inf"), -0.0,
    2 ** 53 - 1, 2 ** 53, 2 ** 53 + 1,
    10 ** 400, -(10 ** 400), _HUGE, -_HUGE,
    Decimal(1), Decimal("nan"), Decimal("Infinity"), Fraction(1, 2),
    True, False, _MyInt(3), _MyFloat(3.0), _Indexy(), _Floaty(),
]

def _hostile_id(value):
    # `repr` on an int past `sys.get_int_max_str_digits()` raises ValueError, and
    # pytest turns that into a collection error for the whole module.
    try:
        return repr(value)
    except ValueError:
        return "huge-int-neg" if value < 0 else "huge-int-pos"


_NUMERIC_SLOTS = [
    ("Int.min", lambda v: Int(min=Min(v))),
    ("Int.max", lambda v: Int(max=Max(v))),
    ("Int.min-exclusive", lambda v: Int(min=Min(v, exclusive=True))),
    ("Int.step", lambda v: Int(step=Step(v))),
    ("Int.multiple_of", lambda v: Int(multiple_of=MultipleOf(v))),
    ("Int.choices", lambda v: Int(choices=Choices(values=(v,)))),
    ("Int.slider", lambda v: Int(min=Min(v), max=Max(v), slider=Slider())),
    ("Float.min", lambda v: Float(min=Min(v))),
    ("Float.max", lambda v: Float(max=Max(v))),
    ("Float.step", lambda v: Float(step=Step(v))),
    ("Float.choices", lambda v: Float(choices=Choices(values=(v,)))),
    ("Str.min", lambda v: Str(min=Min(v))),
    ("Str.max", lambda v: Str(max=Max(v))),
    ("Str.rows", lambda v: Str(rows=Rows(v))),
    ("Str.min_size", lambda v: Str(file_hint=FileHint(min_size=v))),
    ("Str.max_size", lambda v: Str(file_hint=FileHint(max_size=v))),
    ("List.min", lambda v: List(item=(Int(),), min=Min(v))),
    ("List.max", lambda v: List(item=(Int(),), max=Max(v))),
    ("Annotated int Min", lambda v: struct_of(
        make_dataclass("Ai", [("n", Annotated[int, Min(v)])]))),
    ("Annotated int Step", lambda v: struct_of(
        make_dataclass("As", [("n", Annotated[int, Step(v)])]))),
    ("Annotated float Min", lambda v: struct_of(
        make_dataclass("Af", [("x", Annotated[float, Min(v)])]))),
    ("Annotated float Max", lambda v: struct_of(
        make_dataclass("Ag", [("x", Annotated[float, Max(v)])]))),
    ("Annotated float Step", lambda v: struct_of(
        make_dataclass("Ah", [("x", Annotated[float, Step(v)])]))),
    ("Annotated str Min", lambda v: struct_of(
        make_dataclass("At", [("s", Annotated[str, Min(v)])]))),
]


@pytest.mark.parametrize("name, build", _NUMERIC_SLOTS, ids=[n for n, _ in _NUMERIC_SLOTS])
@pytest.mark.parametrize("value", _HOSTILE_NUMBERS, ids=_hostile_id)
def test_a_numeric_atom_is_accepted_or_refused_within_the_vocabulary(
        name, build, value):
    # `math.isfinite` on an int outside the float range raises OverflowError, and
    # `_finite` is the only thing keeping that out. Anything reaching a caller
    # that is neither TypeError nor ValueError breaks the whole error contract.
    try:
        build(value)
    except (TypeError, ValueError):
        pass


@seed(20260808)
@settings(max_examples=400, deadline=None)
@given(
    slot=st.sampled_from(range(len(_NUMERIC_SLOTS))),
    value=st.one_of(
        st.integers(),
        st.integers(min_value=10 ** 300, max_value=10 ** 320),
        st.integers(min_value=-(10 ** 320), max_value=-(10 ** 300)),
        st.floats(),
        st.booleans(),
        st.decimals(allow_nan=True, allow_infinity=True),
        st.fractions(),
    ),
)
def test_generated_numbers_never_escape_the_error_vocabulary(slot, value):
    _, build = _NUMERIC_SLOTS[slot]
    try:
        build(value)
    except (TypeError, ValueError):
        pass


def test_a_float_bound_written_as_an_out_of_range_int_is_a_value_error():
    with pytest.raises(ValueError, match="must be finite"):
        Float(min=Min(10 ** 400))
    with pytest.raises(ValueError, match="must be finite"):
        Float(max=Max(-(10 ** 400)))
    with pytest.raises(ValueError, match="must be finite"):
        Float(step=Step(10 ** 400))


def test_float_and_int_agree_on_the_type_of_a_step():
    # Fix B added the type check `Int` already had. Both now refuse the other's
    # spelling, and both refuse a non-number, so the asymmetry is only the one
    # the shapes themselves have: an int shape steps by ints.
    with pytest.raises(TypeError, match=r"Int\.step: expected int, got float"):
        Int(step=Step(1.5))
    assert Float(step=Step(1)).step == Step(1)
    assert Float(step=Step(1.5)).step == Step(1.5)
    with pytest.raises(TypeError, match="must be a number"):
        Step("1")


# ---------------------------------------------------------------------------
# C — an accepted schema's document carries no NaN and no Infinity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_step_refuses_every_non_finite_float(bad):
    with pytest.raises(ValueError, match="must be finite"):
        Step(bad)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("slot", ["min", "max", "step", "choices"])
def test_no_non_finite_float_reaches_a_float_shape(slot, bad):
    kwargs = {
        "min": lambda: {"min": Min(bad)},
        "max": lambda: {"max": Max(bad)},
        "step": lambda: {"step": Step(bad)},
        "choices": lambda: {"choices": Choices(values=(bad,))},
    }[slot]
    with pytest.raises((TypeError, ValueError)):
        Float(**kwargs())


def _document_of(shape):
    cls = make_dataclass("Hand", [("v", int)])
    return Struct(cls=cls, fields=(Field(name="v", shape=(shape,)),)).to_dict()


@pytest.mark.parametrize("shape", [
    Float(min=Min(-0.0), max=Max(0.0)),
    Float(min=Min(0), max=Max(1)),
    Float(min=Min(-1.7976931348623157e308), max=Max(1.7976931348623157e308)),
    Float(step=Step(1e-320)),
    Float(choices=Choices(values=(1.0, 2.5))),
    Int(min=Min(-(2 ** 53) - 1), max=Max(2 ** 53 + 1)),
    Int(step=Step(10 ** 400)),
    Int(choices=Choices(values=(10 ** 400,))),
    Str(min=Min(0), max=Max(10 ** 400)),
])
def test_an_accepted_numeric_schema_writes_a_strict_json_document(shape):
    document = _document_of(shape)

    text = json.dumps(document, allow_nan=False)

    assert "NaN" not in text
    assert "Infinity" not in text
    assert json.loads(text) == document


def test_no_float_in_a_document_is_non_finite():
    def walk(node):
        if type(node) is dict:
            for v in node.values():
                yield from walk(v)
        elif type(node) is list:
            for v in node:
                yield from walk(v)
        elif type(node) is float:
            yield node

    for shape in (Float(min=Min(-0.0), max=Max(1e308), step=Step(1e-320)),
                  Float(choices=Choices(values=(-0.0, 1e-320)))):
        assert all(math.isfinite(x) for x in walk(_document_of(shape)))


# ---------------------------------------------------------------------------
# D — routing never runs a key's __eq__
# ---------------------------------------------------------------------------

class _HostileKey:
    """Hash-collides with a reserved key, so any `in`/`get` probe compares it."""

    def __init__(self, target: str, log: list, *, raising: bool):
        self._target = target
        self._log = log
        self._raising = raising

    def __hash__(self):
        return hash(self._target)

    def __eq__(self, other):
        self._log.append(other)
        if self._raising:
            raise RuntimeError("hostile __eq__ ran")
        return False

    def __repr__(self):
        return f"<hostile {self._target!r}>"


@dataclass
class _Variant1:
    a: int = 0


@dataclass
class _Variant2:
    b: int = 0


@dataclass
class _TwoVariants:
    v: _Variant1 | _Variant2 = field(default_factory=_Variant1)


@dataclass
class _ListOfVariants:
    xs: list[_Variant1 | _Variant2] = field(default_factory=list)


@dataclass
class _OneVariant:
    v: _Variant1 = field(default_factory=_Variant1)


@dataclass
class _AmbiguousList:
    xs: list[str] | list[int] = field(default_factory=list)


@pytest.mark.parametrize("target", ["$type", "$value"])
def test_a_wrappable_slot_types_its_keys_before_probing_them(target):
    log: list = []
    schema = struct_of(_AmbiguousList)

    with pytest.raises(SchemaTypeError) as error:
        schema.resolve({"xs": {_HostileKey(target, log, raising=True): 1}})

    assert error.value.leaf == "expected string keys, got _HostileKey"
    assert log == []


@pytest.mark.parametrize("target", ["$type", "$value"])
def test_a_single_struct_slot_types_its_keys_before_probing_them(target):
    log: list = []

    with pytest.raises(SchemaTypeError) as error:
        struct_of(_OneVariant).resolve(
            {"v": {_HostileKey(target, log, raising=True): 1}})

    assert error.value.path == ("v",)
    assert error.value.leaf == "expected string keys, got _HostileKey"
    assert log == []


@pytest.mark.parametrize("target", ["$type", "$value"])
def test_decode_never_probes_a_non_string_key(target):
    log: list = []
    key = _HostileKey(target, log, raising=True)

    decoded = struct_of(_TwoVariants).decode({"v": {key: 1}})

    assert decoded == {"v": {key: 1}}
    assert log == []


@pytest.mark.parametrize("call", ["resolve", "build"])
def test_two_struct_options_type_their_keys_before_probing_them(call):
    log: list = []
    schema = struct_of(_TwoVariants)
    data = {"v": {_HostileKey("$type", log, raising=True): 1}}

    with pytest.raises(SchemaTypeError):
        getattr(schema, call)(data)

    assert log == []


def test_two_struct_options_inside_a_list_type_their_keys_too():
    log: list = []

    with pytest.raises(SchemaTypeError):
        struct_of(_ListOfVariants).resolve(
            {"xs": [{_HostileKey("$type", log, raising=True): 1}]})

    assert log == []


def test_routing_two_struct_options_calls_no_user_eq_at_all():
    # Same hole, counted rather than raised: a non-raising __eq__ shows the probe
    # happening even where the report looks clean.
    log: list = []

    with pytest.raises(SchemaTypeError):
        struct_of(_TwoVariants).resolve(
            {"v": {_HostileKey("$type", log, raising=False): 1}})

    assert log == []


# ---------------------------------------------------------------------------
# E — PEP 678 notes survive a rebuild, at any depth, exactly once
# ---------------------------------------------------------------------------

_BAD_LIST = ["a", 1.5]
_NOTES = [
    "as list[str]: [1]: expected str, got float",
    "as list[int]: [0]: expected int, got str",
]


@dataclass
class _NoteLeaf:
    xs: list[str] | list[int] = field(default_factory=list)


@dataclass
class _NoteMid:
    leaf: _NoteLeaf = field(default_factory=_NoteLeaf)


@dataclass
class _NoteTop:
    mid: _NoteMid = field(default_factory=_NoteMid)
    items: list[list[str] | list[int]] = field(default_factory=list)


@pytest.mark.parametrize("cls, value, path", [
    (_NoteLeaf, lambda: _NoteLeaf(xs=_BAD_LIST), ("xs",)),
    (_NoteMid, lambda: _NoteMid(leaf=_NoteLeaf(xs=_BAD_LIST)), ("leaf", "xs")),
    (_NoteTop, lambda: _NoteTop(mid=_NoteMid(leaf=_NoteLeaf(xs=_BAD_LIST))),
     ("mid", "leaf", "xs")),
    (_NoteTop, lambda: _NoteTop(items=[_BAD_LIST]), ("items", 0)),
])
def test_notes_survive_every_depth_without_duplicating(cls, value, path):
    with pytest.raises(SchemaValueError) as error:
        struct_of(cls)._check(value())

    assert error.value.path == path
    assert error.value.leaf == "matches no option: list[str] | list[int]"
    # A note repeated once per level walked would be a defect of its own.
    assert error.value.__notes__ == _NOTES


def test_notes_survive_compile_time_certification():
    holder = make_dataclass("Certified", [
        ("xs", list[str] | list[int],
         field(default_factory=lambda: ["a", 1.5]))])

    with pytest.raises(SchemaValueError) as error:
        struct_of(holder)

    assert error.value.path == ("xs", "default")
    assert error.value.__notes__ == _NOTES


class _Flip:
    """Pure for certification, impure afterwards, so the serving path reports."""

    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return ["a"] if self.calls == 1 else ["a", 1.5]


def test_notes_survive_a_default_served_at_resolve_time():
    served = make_dataclass("Served", [
        ("xs", list[str] | list[int], field(default_factory=_Flip()))])
    schema = struct_of(served)

    with pytest.raises(SchemaValueError) as error:
        schema.resolve({})

    assert error.value.path == ("xs", "default")
    assert error.value.__notes__ == _NOTES


def test_notes_survive_pickle_after_being_carried_two_levels_out():
    with pytest.raises(SchemaValueError) as error:
        struct_of(_NoteMid)._check(_NoteMid(leaf=_NoteLeaf(xs=_BAD_LIST)))

    revived = pickle.loads(pickle.dumps(error.value))

    assert revived.__notes__ == _NOTES
    assert revived.path == ("leaf", "xs")
    assert revived.leaf == "matches no option: list[str] | list[int]"
    assert str(revived) == "leaf: xs: matches no option: list[str] | list[int]"


def _noisy_factory():
    error = ValueError("factory blew up")
    error.add_note("the factory explained itself")
    raise error


def test_a_factory_error_keeps_its_notes_through_certification():
    holder = make_dataclass(
        "Noisy", [("n", int, field(default_factory=_noisy_factory))])

    with pytest.raises(TypeError) as error:
        struct_of(holder)

    assert error.value.__notes__ == ["the factory explained itself"]


class _NoisyOnce:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.calls == 1:
            return 1
        error = KeyError("boom")
        error.add_note("the factory explained itself")
        raise error


def test_a_factory_error_keeps_its_notes_when_a_default_is_served():
    served = make_dataclass("NoisyServed", [
        ("n", int, field(default_factory=_NoisyOnce()))])
    schema = struct_of(served)

    with pytest.raises(SchemaValueError) as error:
        schema.resolve({})

    assert error.value.path == ("n", "default")
    assert error.value.__notes__ == ["the factory explained itself"]

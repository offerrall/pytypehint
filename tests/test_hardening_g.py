"""Regression tests for promises the suite stated but did not pin.

Every test here was written because a deliberate, wrong change to `src/` passed
`python -m pytest -q` untouched. Each one names the mutation it kills, so the
reason it exists survives the next refactor.
"""

import enum
from dataclasses import field, make_dataclass
from datetime import date, time
from pathlib import Path
from typing import Annotated

import pytest

from pytypehint import (
    FileHint, SchemaTypeError, SchemaValueError, Step, Struct, signature_of,
    struct_of,
)
from pytypehint.shapes import Float, Int, Str
from pytypehint.structure import _DATE_TEXT, _TIME_TEXT, Field

# ---------------------------------------------------------------------------
# 1. `to_dict()` must not raise on a schema the core accepted
#
# Kills: contract._as_float with its OverflowError arm removed.
#
# `Float` checks the type and finiteness of `min` and `max` but not of `step`,
# so `Step(10 ** 400)` compiles: it is an int, and it is positive. The emitter
# then writes a float node, where every number is normalised to a float so that
# `Min(0)` and `Min(0.0)` — equal atoms — cannot produce two documents. There is
# no float of that value to normalise to, and the document must still be written.
# ---------------------------------------------------------------------------

_TOO_BIG_FOR_A_FLOAT = 10 ** 400


def _float_node(annotation):
    schema = struct_of(make_dataclass("_Probe", [("value", annotation)]))
    root = schema.to_dict()["defs"]["structs"]["_Probe"]
    return root["fields"][0]["shape"][0]


def test_a_float_step_beyond_the_float_range_is_refused_at_compilation():
    # This test used to assert the opposite — that the step was written through as
    # an int — which was the symptom of `Float` checking finiteness for min, max
    # and choices but not for step. A step no float equals names no float, so the
    # shape refuses it where it refuses the other three.
    with pytest.raises(ValueError, match="step: must be finite"):
        _float_node(Annotated[float, Step(_TOO_BIG_FOR_A_FLOAT)])


def test_a_hand_built_float_shape_cannot_hold_an_unfloatable_step_either():
    # The shape is where the rule lives, so hand construction cannot route around
    # it: there is no way to reach `to_dict` with such a step at all.
    with pytest.raises(ValueError, match="step: must be finite"):
        Float(step=Step(value=_TOO_BIG_FOR_A_FLOAT))


# ---------------------------------------------------------------------------
# 2. decode is total, including at the top level
#
# Kills: structure._decode_fields with its `type(key) is str` guard removed.
#
# `_decode_dict` refuses to look a non-string key up because the lookup would
# run the key's own `__eq__` on a hash collision — arbitrary code, on a path
# that has to be total — and that guard is covered. Its twin in
# `_decode_fields`, which is what `Struct.decode` and `Signature.decode` enter
# through, was not: a hostile key in the outermost dict reached the lookup.
# ---------------------------------------------------------------------------

class _HostileKey:
    """Hashes onto a real field name and explodes when compared to anything."""

    def __hash__(self):
        return hash("value")

    def __eq__(self, other):
        raise RuntimeError("__eq__ must never be reached by a decode lookup")


def test_decode_does_not_compare_a_hostile_top_level_key_against_a_field_name():
    schema = struct_of(make_dataclass("_Top", [("value", int)]))
    key = _HostileKey()

    decoded = schema.decode({key: 1})

    assert len(decoded) == 1
    assert next(iter(decoded)) is key
    assert decoded[key] == 1


def test_signature_decode_does_not_compare_a_hostile_top_level_key_either():
    def handler(value: int) -> None:
        ...

    schema = signature_of(handler)
    key = _HostileKey()

    decoded = schema.decode({key: 1})

    assert len(decoded) == 1
    assert next(iter(decoded)) is key


def test_a_hostile_key_beside_a_real_one_leaves_the_real_one_decoded():
    schema = struct_of(make_dataclass("_Mixed", [("when", date)]))
    key = _HostileKey()

    decoded = schema.decode({"when": "2026-08-08", key: 1})

    assert decoded["when"] == date(2026, 8, 8)
    assert decoded[key] == 1


# ---------------------------------------------------------------------------
# 3. The canonical spellings are pinned here, not delegated to the parser
#
# Kills: structure._DATE_TEXT / _TIME_TEXT compiled without re.ASCII.
#
# `\d` without re.ASCII admits every decimal digit Unicode defines. Today
# `date.fromisoformat` refuses those anyway, so the mutation is invisible from
# the outside — which is exactly the coupling the flag exists to break. The
# spelling is the core's promise, so it is asserted on the spelling.
# ---------------------------------------------------------------------------

_ARABIC_INDIC_DATE = "٢٠٢٦-٠٨-٠٨"
_ARABIC_INDIC_TIME = "١٤:٣٠"
_FULLWIDTH_DATE = "２０２６-０８-０８"


@pytest.mark.parametrize("text", [_ARABIC_INDIC_DATE, _FULLWIDTH_DATE],
                         ids=["arabic_indic", "fullwidth"])
def test_a_non_ascii_digit_string_is_not_a_date_spelling(text):
    assert _DATE_TEXT.fullmatch(text) is None


def test_a_non_ascii_digit_string_is_not_a_time_spelling():
    assert _TIME_TEXT.fullmatch(_ARABIC_INDIC_TIME) is None


def test_the_ascii_spellings_are_still_the_accepted_ones():
    assert _DATE_TEXT.fullmatch("2026-08-08") is not None
    assert _TIME_TEXT.fullmatch("14:30") is not None
    assert _TIME_TEXT.fullmatch("14:30:00") is not None


@pytest.mark.parametrize("annotation, text",
                         [(date, _ARABIC_INDIC_DATE), (time, _ARABIC_INDIC_TIME)],
                         ids=["date", "time"])
def test_a_non_ascii_digit_spelling_is_handed_back_as_a_str(annotation, text):
    schema = struct_of(make_dataclass("_Wire", [("value", annotation)]))

    assert schema.decode({"value": text})["value"] is text


# ---------------------------------------------------------------------------
# 4. A union reports the options it actually offers
#
# Kills: validation.check_options_value routing with isinstance instead of
# `type(value) is shape.pytype`.
#
# `bool` is a subclass of `int`, so isinstance would elect `Int` as the single
# candidate for `True` on an `int | str` slot and let it report its own,
# narrower failure. The slot accepts two types and the message says so.
# ---------------------------------------------------------------------------

def test_a_bool_default_on_an_int_or_str_field_names_both_options():
    with pytest.raises(SchemaTypeError) as error:
        struct_of(make_dataclass(
            "_Union", [("value", int | str, field(default=True))]))

    assert error.value.leaf == "expected int | str, got bool"
    assert error.value.path == ("value", "default")
    assert str(error.value) == "value: default: expected int | str, got bool"


def test_a_bool_instance_on_an_int_or_str_field_names_both_options():
    cls = make_dataclass("_Instance", [("value", int)])
    schema = Struct(cls=cls, fields=(
        Field(name="value", shape=(Int(), Str())),
    ))

    with pytest.raises(SchemaTypeError) as error:
        schema._check(cls(True))

    assert error.value.leaf == "expected int | str, got bool"
    assert error.value.path == ("value",)


def test_an_int_enum_member_on_an_int_or_str_field_names_both_options():
    class Level(enum.IntEnum):
        HIGH = 1

    cls = make_dataclass("_Enumish", [("value", int)])
    schema = Struct(cls=cls, fields=(
        Field(name="value", shape=(Int(), Str())),
    ))

    with pytest.raises(SchemaTypeError) as error:
        schema._check(cls(Level.HIGH))

    assert error.value.leaf == "expected int | str, got Level"


# ---------------------------------------------------------------------------
# 5. Nothing decode returns is a container the caller handed in
#
# Kills: structure._decode_fields returning a non-dict `data` uncopied.
#
# "Everything decode returns is freshly built, so the caller's tree is never
# touched and the result is never wired back into it." The tests that state this
# feed a dict at the top, so the one arm that answers a non-dict — which is what
# `Struct.decode` and `Signature.decode` reach first — went unchecked.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tree", [[1, 2], [{"value": 1}], []],
                         ids=["list", "list_of_dict", "empty"])
def test_a_top_level_non_dict_is_copied_and_not_handed_straight_back(tree):
    schema = struct_of(make_dataclass("_NonDict", [("value", int)]))

    decoded = schema.decode(tree)

    assert decoded == tree
    assert decoded is not tree


def test_a_signature_also_copies_a_top_level_non_dict():
    def handler(value: int) -> None:
        ...

    tree = [1, 2]
    decoded = signature_of(handler).decode(tree)

    assert decoded == tree
    assert decoded is not tree


def test_a_nested_container_of_a_top_level_non_dict_is_copied_too():
    schema = struct_of(make_dataclass("_Deep", [("value", int)]))
    inner = {"value": 1}
    tree = [inner]

    decoded = schema.decode(tree)

    assert decoded[0] == inner
    assert decoded[0] is not inner


# ---------------------------------------------------------------------------
# 6. `FileHint` judges the text, never the world the text points at
#
# Kills: shapes._check_file_hint reaching for the filesystem again.
#
# The mark used to `stat()` the path it was handed, so the answer depended on
# what sat on disk at the instant the check ran. It now reads the extension out
# of the string and states the sizes for the boundary that holds the file. The
# tests that replaced the old ones assert on values that happen to exist, so a
# `Path.stat` creeping back would leave them green. This states the rule where
# it can only be broken deliberately: whatever the value names, nothing looks.
# ---------------------------------------------------------------------------

def test_the_file_mark_settles_a_value_without_touching_the_filesystem(monkeypatch):
    def forbidden(self, *args, **kwargs):
        raise AssertionError("FileHint consulted the filesystem")

    for reader in ("stat", "lstat", "exists", "is_file", "is_dir", "open"):
        monkeypatch.setattr(Path, reader, forbidden)

    mark = Str(file_hint=FileHint(extensions=(".png",), min_size=1, max_size=100))

    # Accepted on its spelling alone, whether or not any such file is there.
    mark._check("report.png")
    mark._check("/no/such/directory/report.png")
    # The sizes are stated for the reader, not tested here: no size can fail.
    Str(file_hint=FileHint(min_size=10 ** 9))._check("gone.png")

    with pytest.raises(SchemaValueError) as error:
        mark._check("report.txt")
    assert error.value.leaf == (
        "not an accepted file type: 'report.txt', expected one of ('.png',)")

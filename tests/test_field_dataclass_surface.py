"""Field's internal bookkeeping is declared, so the stdlib dataclass helpers see a complete class."""

import dataclasses
from dataclasses import dataclass
from typing import Annotated

import pytest

from pytypehint import Label, Min, struct_of
from pytypehint.structure import Field
from pytypehint.utils import MISSING


@dataclass
class _Page:
    size: Annotated[int, Min(1)] = 20
    label: str = "page"


def _field(name="size"):
    return next(f for f in struct_of(_Page).fields if f.name == name)


def test_field_repr_hides_the_internal_bookkeeping():
    """README, 'Public API': Field is inspectable surface; _recipe and _deferred are machinery and stay out of its repr."""
    text = repr(_field())

    assert text.startswith("Field(")
    assert "_recipe" not in text
    assert "_deferred" not in text


def test_field_repr_shows_the_documented_attributes():
    """README, 'Public API': `Field` is exported for inspection, so its repr must show what it inspects."""
    text = repr(_field())

    assert "name='size'" in text
    assert "default=20" in text


def test_dataclasses_replace_rebuilds_a_field():
    """README, 'Guarantees': `Field` is a plain frozen dataclass; replace must not trip over its internals."""
    original = _field()

    clone = dataclasses.replace(original, name="renamed")

    assert clone.name == "renamed"
    assert clone.shape == original.shape
    assert clone.default == 20


def test_dataclasses_replace_recomputes_the_recipe():
    """docs/defaults.md: 'A default is a recipe' — a rebuilt Field must certify its own default, not inherit a stale one."""
    original = _field()

    clone = dataclasses.replace(original, default=50)

    assert clone.default == 50
    assert clone._recipe == 50
    assert clone._deferred is False


def test_replace_rejects_setting_the_internals_directly():
    """The bookkeeping is init=False: it is derived from `default`, never supplied."""
    original = _field()

    # 3.13 raises TypeError here; older CPython raised ValueError. The rule under
    # test is the refusal, not which of the two the stdlib picks.
    with pytest.raises((TypeError, ValueError)) as error:
        dataclasses.replace(original, _recipe=99)

    assert "_recipe" in str(error.value)


def test_internals_are_declared_fields_and_excluded_from_comparison():
    """structure.Str._compiled sets the house style: derived state is a declared field, hidden from repr and comparison."""
    names = {f.name: f for f in dataclasses.fields(Field)}

    assert set(names) >= {"_recipe", "_deferred"}
    for name in ("_recipe", "_deferred"):
        assert names[name].init is False
        assert names[name].repr is False
        assert names[name].compare is False


def test_field_without_a_default_keeps_missing_as_its_recipe():
    """docs/defaults.md: a field with no default has no recipe to run."""
    @dataclass
    class Required:
        n: int

    f = struct_of(Required).fields[0]

    assert f.default is MISSING
    assert f._recipe is MISSING


def test_asdict_walks_a_field_without_exploding():
    """`Field` is a plain dataclass, so the stdlib walkers must survive it."""
    f = struct_of(_Page).fields[1]

    data = dataclasses.asdict(f)

    assert data["name"] == "label"
    assert data["default"] == "page"


def test_field_identity_equality_survives_the_declaration():
    """README, 'Guarantees': '`Struct`, `Field` and `Signature` compare by identity'."""
    first = _field()
    second = _field()

    assert first == first
    assert first != second


def test_label_still_rides_on_the_field():
    """docs/atoms.md: 'Label(text) and Description(text) are non-empty field-level notation'."""
    @dataclass
    class C:
        x: Annotated[int, Label("X")] = 0

    assert struct_of(C).fields[0].label == Label("X")

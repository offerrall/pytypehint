"""The atom->field table of bridge._atoms_of, checked against docs/atoms.md."""

from dataclasses import dataclass, fields as dc_fields, make_dataclass
from datetime import date, time
from enum import Enum
from typing import Annotated, get_type_hints

import pytest

from pytypehint import (
    Choices, Extra, IsPassword, IsPathFile, Max, Min, MultipleOf, Pattern,
    Placeholder, Rows, Slider, Step, struct_of,
)
from pytypehint import bridge


# ---------------------------------------------------------------- invariant


@pytest.mark.parametrize("pytype", list(bridge._VOCABULARY), ids=lambda t: t.__name__)
def test_atom_table_maps_each_atom_type_to_exactly_one_field(pytype):
    """docs/atoms.md gives each shape one accepted-atom set; a repeated atom type would be dropped in silence.

    This test deliberately inspects internals: bridge._atoms_of builds a
    dict keyed by atom type, so two fields hinted with the same atom type
    would collapse into one entry with no error anywhere. Nothing in the
    public surface can observe that, which is exactly why it is pinned here.
    """
    shape_cls, table = bridge._VOCABULARY[pytype]

    hints = get_type_hints(shape_cls)
    atom_fields = [(f.name, atom) for f in dc_fields(shape_cls)
                   if (atom := bridge._atom_type(hints[f.name])) is not None]

    atom_types = [atom for _, atom in atom_fields]
    duplicates = sorted({a.__name__ for a in atom_types if atom_types.count(a) > 1})
    assert not duplicates, (
        f"{shape_cls.__name__} hints the same atom type on more than one field "
        f"({', '.join(duplicates)}); bridge._atoms_of would keep only the last "
        f"and silently ignore the rest")

    # Extra is the one atom with no field hinted `Extra | None`: it merges into
    # `_extras`, which bridge._atoms_of appends to the table by hand.
    expected = len(atom_fields) + (1 if Extra in table else 0)
    assert len(table) == expected, (
        f"{shape_cls.__name__}: table has {len(table)} entries for "
        f"{expected} atom-hinted fields — an entry was overwritten")


# ------------------------------------------------------- docs/atoms.md matrix


class _Color(Enum):
    RED = 1


@dataclass
class _Inner:
    n: int = 1


def _int_hint(meta):
    return Annotated[tuple([int, *meta])]


def _float_hint(meta):
    return Annotated[tuple([float, *meta])]


def _str_hint(meta):
    return Annotated[tuple([str, *meta])]


def _date_hint(meta):
    return Annotated[tuple([date, *meta])]


def _time_hint(meta):
    return Annotated[tuple([time, *meta])]


def _bool_hint(meta):
    return Annotated[tuple([bool, *meta])]


def _list_hint(meta):
    return Annotated[tuple([list[int], *meta])]


def _none_hint(meta):
    # None alone is optionality, never a field type: reach NoneShape through a union.
    return int | Annotated[tuple([type(None), *meta])]


def _enum_hint(meta):
    return Annotated[tuple([_Color, *meta])]


def _dataclass_hint(meta):
    return Annotated[tuple([_Inner, *meta])]


# Every type atom in the vocabulary, with one canonical instance each. Field
# atoms (Label, Description, OptionalToggle) are excluded: docs/atoms.md accepts
# them on "any field" / "optional field", and bridge._field_of strips them
# before a shape is ever compiled.
_TYPE_ATOMS = {
    Min: Min(0),
    Max: Max(10),
    Choices: Choices(values=(1, 2)),
    MultipleOf: MultipleOf(2),
    Pattern: Pattern("[a-z]+"),
    Step: Step(1),
    Slider: Slider(),
    Placeholder: Placeholder("p"),
    Rows: Rows(2),
    IsPassword: IsPassword(),
    IsPathFile: IsPathFile(extensions=(".txt",)),
    Extra: Extra("pkg.k", "e"),
}

# docs/atoms.md, "Accepted atoms" table. Each documented atom maps to the full
# metadata tuple needed to compile it — Slider carries the Min and Max that
# "sliders without both bounds" would otherwise reject at compile time, and
# Choices carries values of the shape's exact type.
_MATRIX = [
    ("int", int, _int_hint, {
        Min: (Min(0),),
        Max: (Max(10),),
        Choices: (Choices(values=(1, 2)),),
        MultipleOf: (MultipleOf(2),),
        Step: (Step(1),),
        Slider: (Min(0), Max(10), Slider()),
        Placeholder: (Placeholder("p"),),
        Extra: (Extra("pkg.k", "e"),),
    }),
    ("float", float, _float_hint, {
        Min: (Min(0.0),),
        Max: (Max(10.0),),
        Choices: (Choices(values=(1.0, 2.0)),),
        Step: (Step(1.0),),
        Slider: (Min(0.0), Max(10.0), Slider()),
        Placeholder: (Placeholder("p"),),
        Extra: (Extra("pkg.k", "e"),),
    }),
    ("str", str, _str_hint, {
        Min: (Min(0),),
        Max: (Max(10),),
        Choices: (Choices(values=("a", "b")),),
        Pattern: (Pattern("[a-z]+"),),
        IsPathFile: (IsPathFile(extensions=(".txt",)),),
        IsPassword: (IsPassword(),),
        Rows: (Rows(2),),
        Placeholder: (Placeholder("p"),),
        Extra: (Extra("pkg.k", "e"),),
    }),
    ("date", date, _date_hint, {
        Min: (Min(date(2000, 1, 1)),),
        Max: (Max(date(2030, 1, 1)),),
        Choices: (Choices(values=(date(2020, 1, 1),)),),
        Placeholder: (Placeholder("p"),),
        Extra: (Extra("pkg.k", "e"),),
    }),
    ("time", time, _time_hint, {
        Min: (Min(time(0, 0)),),
        Max: (Max(time(23, 0)),),
        Choices: (Choices(values=(time(12, 0),)),),
        Placeholder: (Placeholder("p"),),
        Extra: (Extra("pkg.k", "e"),),
    }),
    ("list", list, _list_hint, {
        Min: (Min(0),),
        Max: (Max(10),),
        Extra: (Extra("pkg.k", "e"),),
    }),
    ("bool", bool, _bool_hint, {
        Extra: (Extra("pkg.k", "e"),),
    }),
    ("NoneType", type(None), _none_hint, {
        Extra: (Extra("pkg.k", "e"),),
    }),
    ("enum", _Color, _enum_hint, {
        Extra: (Extra("pkg.k", "e"),),
    }),
    ("dataclass", None, _dataclass_hint, {}),
]


def _field_of(hint):
    return struct_of(make_dataclass("C", [("x", hint)])).fields[0]


def _accepted_cases():
    for kind, pytype, hint_of, documented in _MATRIX:
        for atom_cls, meta in documented.items():
            yield pytest.param(kind, pytype, hint_of, atom_cls, meta,
                               id=f"{kind}-{atom_cls.__name__}")


def _rejected_cases():
    for kind, pytype, hint_of, documented in _MATRIX:
        for atom_cls, atom in _TYPE_ATOMS.items():
            if atom_cls in documented:
                continue
            yield pytest.param(kind, hint_of, atom, id=f"{kind}-{atom_cls.__name__}")


@pytest.mark.parametrize("kind, pytype, hint_of, atom_cls, meta", list(_accepted_cases()))
def test_documented_atom_is_accepted(kind, pytype, hint_of, atom_cls, meta):
    """docs/atoms.md: the 'Accepted atoms' table lists this atom for this shape."""
    field = _field_of(hint_of(meta))

    shape = next(s for s in field.shape if s.pytype is pytype)
    # Extra maps to "_extras" on every shape, including EnumShape which lives
    # outside bridge._VOCABULARY.
    attribute = ("_extras" if atom_cls is Extra
                 else bridge._VOCABULARY[pytype][1][atom_cls])
    # Extra is stored merged, so the atom does not survive as itself.
    expected = (((meta[-1].key, meta[-1].value),) if atom_cls is Extra else meta[-1])
    assert getattr(shape, attribute) == expected


@pytest.mark.parametrize("kind, hint_of, atom", list(_rejected_cases()))
def test_undocumented_atom_is_rejected(kind, hint_of, atom):
    """docs/atoms.md: absent from this shape's row, so 'Unsupported metadata reports `unsupported metadata for <type>: <atom>`'."""
    with pytest.raises(TypeError) as error:
        _field_of(hint_of((atom,)))

    # docs/atoms.md fixes the message shape; repr is the observed rendering of <atom>.
    assert str(error.value) == f"unsupported metadata for {kind}: {atom!r}"


def test_matrix_covers_every_type_atom_in_the_vocabulary():
    """docs/atoms.md is the full atom vocabulary; a new atom must land in the table above."""
    field_atoms = set(bridge._FIELD_ATOMS)
    assert set(_TYPE_ATOMS) == bridge._ATOM_CLASSES - field_atoms


def test_matrix_covers_every_shape_in_the_vocabulary():
    """docs/atoms.md rows must account for every shape bridge can compile."""
    covered = {kind for kind, *_ in _MATRIX}
    expected = {t.__name__ for t in bridge._VOCABULARY} | {"enum", "dataclass"}
    assert covered == expected

"""Properties of bridge._field_of: Annotated layering and field-atom hoisting out of union options.

typing flattens nested Annotated in ways that have shifted between versions, so
these are equivalence properties over the *compiled* Field, not assertions about
how a hint happens to be spelled.
"""

from dataclasses import field, make_dataclass
from typing import Annotated

import pytest
from hypothesis import given, settings, strategies as st

from pytypehint import (
    Description, Label, Max, Min, OptionalToggle, struct_of,
)
from pytypehint.shapes import Int, NoneShape, Str


def _field(hint):
    """Compile a single required field carrying `hint`."""
    return struct_of(make_dataclass("C", [("x", hint)])).fields[0]


def _summary(f):
    """Everything observable about a Field. Field itself compares by identity."""
    return (f.shape, f.label, f.description, f.optional_toggle)


# --------------------------------------------------- nested == flat Annotated


def test_nested_annotated_compiles_like_flat_annotated():
    """docs/atoms.md, 'Layering': layering an alias is spelled differently but means the same schema."""
    nested = _field(Annotated[Annotated[int, Min(0)], Max(10)])
    flat = _field(Annotated[int, Min(0), Max(10)])

    assert _summary(nested) == _summary(flat)
    assert nested.shape == (Int(min=Min(0), max=Max(10)),)


def test_docs_layering_example_narrow_overrides_percent():
    """docs/atoms.md, 'Layering': Narrow = Annotated[Percent, Max(50)] over Percent = Annotated[int, Min(0), Max(100)]."""
    percent = Annotated[int, Min(0), Max(100)]
    narrow = Annotated[percent, Max(50)]

    f = _field(narrow)

    assert f.shape == (Int(min=Min(0), max=Max(50)),)


def test_docs_layering_example_closed_overrides_optional_toggle():
    """docs/atoms.md, 'Layering': the rule 'applies uniformly to limits and field notation'."""
    optional = Annotated[int | None, OptionalToggle(True)]
    closed = Annotated[optional, OptionalToggle(False)]

    assert _field(closed).optional_toggle == OptionalToggle(False)


# ------------------------------------------------------------ bound layering


def test_layered_bounds_outer_wins():
    """docs/atoms.md, 'Layering': 'For repeated atom classes, the outer layer wins'."""
    f = _field(Annotated[Annotated[int, Max(100)], Max(50)])

    assert f.shape[0].max == Max(50)

    struct = struct_of(make_dataclass("C", [("x", Annotated[Annotated[int, Max(100)], Max(50)])]))
    assert struct.build({"x": 50}).x == 50
    with pytest.raises(ValueError) as error:
        struct.build({"x": 60})
    assert str(error.value) == "x: too large: 60, maximum 50"


def test_flat_bounds_rightmost_wins():
    """docs/atoms.md, 'Layering': 'within one layer, the rightmost atom wins' — observed: Max(50) is the effective bound.

    Observed behaviour, pinned: bridge._kwargs_of assigns kwargs[name] = m while
    walking the metadata left to right, so the last Max of the layer survives and
    Max(100) is discarded. It is not an error and no warning is emitted.
    """
    f = _field(Annotated[int, Max(100), Max(50)])

    assert f.shape[0].max == Max(50)

    struct = struct_of(make_dataclass("C", [("x", Annotated[int, Max(100), Max(50)])]))
    assert struct.build({"x": 50}).x == 50
    with pytest.raises(ValueError) as error:
        struct.build({"x": 60})
    assert str(error.value) == "x: too large: 60, maximum 50"


def test_outer_wins_and_rightmost_wins_coincide_because_typing_flattens_outward():
    """docs/atoms.md, 'Layering': the two halves of the rule agree because typing appends the outer layer to the right."""
    from typing import get_args

    assert get_args(Annotated[Annotated[int, Max(100)], Max(50)]) == (int, Max(100), Max(50))
    assert _summary(_field(Annotated[Annotated[int, Max(100)], Max(50)])) == \
           _summary(_field(Annotated[int, Max(100), Max(50)]))


# ------------------------------------------------- hoisting out of a union


_NAMED = Annotated[int, Label("n")]


def test_label_in_alias_is_hoisted_out_of_an_optional_union():
    """docs/atoms.md: field notation applies to 'any field', so an alias inside `X | None` still labels the field."""
    f = _field(_NAMED | None)

    assert f.label == Label("n")
    assert f.shape == (Int(), NoneShape())


def test_conflicting_labels_across_union_options_are_rejected():
    """docs/atoms.md: 'Conflicting field atoms hoisted from different union options fail with `conflicting ... across union options`'."""
    with pytest.raises(TypeError) as error:
        _field(Annotated[int, Label("A")] | Annotated[str, Label("B")])

    assert "conflicting labels across union options" in str(error.value)


def test_conflicting_descriptions_across_union_options_are_rejected():
    """docs/atoms.md: the conflict rule covers field notation generally, not just Label."""
    with pytest.raises(TypeError) as error:
        _field(Annotated[int, Description("X")] | Annotated[str, Description("Y")])

    assert "conflicting descriptions across union options" in str(error.value)


def test_explicit_outer_label_overrides_conflicting_hoisted_labels():
    """docs/atoms.md: 'an explicit outer atom overrides them'."""
    f = _field(Annotated[Annotated[int, Label("A")] | Annotated[str, Label("B")], Label("Outer")])

    assert f.label == Label("Outer")
    assert f.shape == (Int(), Str())


def test_equal_labels_across_union_options_do_not_conflict():
    """docs/atoms.md: only *conflicting* atoms fail; atoms are frozen values and compare by value."""
    f = _field(Annotated[int, Label("Same")] | Annotated[str, Label("Same")])

    assert f.label == Label("Same")


def test_equal_labels_from_distinct_instances_do_not_conflict():
    """docs/atoms.md: 'Atoms are frozen values' — equality, not identity, decides the conflict."""
    left = Label("Same")
    right = Label("Same")
    assert left is not right

    assert _field(Annotated[int, left] | Annotated[str, right]).label == Label("Same")


# ------------------------------------------------------- metadata placement


def test_type_metadata_on_a_multi_type_union_is_rejected():
    """docs/atoms.md: 'Metadata across a multi-type union must be placed per option'."""
    with pytest.raises(TypeError) as error:
        _field(Annotated[int | str, Min(0)])

    assert "metadata on a union of multiple types must go per option" in str(error.value)


def test_type_metadata_per_union_option_is_accepted():
    """docs/atoms.md: the same constraint placed per option is the documented spelling."""
    f = _field(Annotated[int, Min(0)] | str)

    assert f.shape == (Int(min=Min(0)), Str())


def test_type_metadata_on_pure_none_is_rejected():
    """docs/restrictions.md, 'Bare `None`': '`None` expresses optionality; it needs a real value option'."""
    with pytest.raises(TypeError) as error:
        _field(Annotated[None, Min(0)])

    assert "metadata on None: None is optionality, not a type" in str(error.value)


def test_type_metadata_on_a_single_optional_targets_the_real_option():
    """docs/atoms.md: with one real option beside None, metadata is unambiguous and lands on that option."""
    f = _field(Annotated[int | None, Min(0)])

    assert f.shape == (Int(min=Min(0)), NoneShape())


# ------------------------------------------------------- OptionalToggle


def test_optional_toggle_in_alias_is_hoisted_when_the_alias_is_unioned_with_none():
    """docs/atoms.md: 'OptionalToggle(enabled) is field-level notation for `X | None`' — observed: hoisting succeeds.

    Observed behaviour, pinned: the toggle rides inside the alias, so at hoisting
    time bridge._field_of has already split the union and NoneShape is among the
    options. Field.__post_init__ therefore finds the optional field it requires
    and the toggle survives. It does *not* fail.
    """
    T = Annotated[int, OptionalToggle(True)]

    f = _field(T | None)

    assert f.optional_toggle == OptionalToggle(True)
    assert f.shape == (Int(), NoneShape())


def test_optional_toggle_in_alias_without_none_is_rejected():
    """docs/atoms.md, 'Compile-time cross-checks': '`OptionalToggle` on a non-optional field' is a contradiction."""
    T = Annotated[int, OptionalToggle(True)]

    with pytest.raises(TypeError) as error:
        _field(T)

    assert "OptionalToggle requires an optional field (X | None)" in str(error.value)


def test_optional_toggle_never_changes_resolution_or_defaults():
    """docs/atoms.md: 'It never changes resolution or defaults'."""
    T = Annotated[int, OptionalToggle(False)]
    struct = struct_of(make_dataclass("C", [("x", T | None, field(default=None))]))

    assert struct.resolve({}) == {"x": None}
    assert struct.resolve({"x": 3}) == {"x": 3}
    assert struct.build({}).x is None


# --------------------------------------------------- field atoms in list items


def test_field_atoms_in_list_items_are_rejected():
    """docs/restrictions.md, 'Field atoms inside list items': 'field atoms cannot apply to list items'."""
    with pytest.raises(TypeError) as error:
        _field(list[Annotated[int, Label("n")]])

    assert str(error.value) == "field atoms cannot apply to list items"


def test_field_atoms_reaching_list_items_through_an_alias_are_rejected():
    """docs/restrictions.md: 'List items have type constraints but no independent field presentation' — an alias is no loophole."""
    with pytest.raises(TypeError) as error:
        _field(list[_NAMED])

    assert str(error.value) == "field atoms cannot apply to list items"


@pytest.mark.parametrize("atom", [Label("n"), Description("d"), OptionalToggle(True)],
                         ids=lambda a: type(a).__name__)
def test_every_field_atom_is_rejected_inside_list_items(atom):
    """docs/atoms.md: Label, Description and OptionalToggle are the field atoms; none of them describes an item."""
    alias = Annotated[tuple([int, atom])]

    with pytest.raises(TypeError) as error:
        _field(list[alias])

    assert str(error.value) == "field atoms cannot apply to list items"


def test_type_atoms_in_list_items_are_accepted():
    """docs/atoms.md: 'List items have type constraints' — only field notation is barred."""
    f = _field(list[Annotated[int, Min(0)]])

    assert f.shape[0].item == (Int(min=Min(0)),)


def test_field_atoms_on_the_list_itself_are_accepted():
    """docs/atoms.md: a list field is still 'any field', so Label belongs on the list, not on its items."""
    f = _field(Annotated[list[int], Label("n")])

    assert f.label == Label("n")


# ------------------------------------------------------- hypothesis property


_MINS = [Min(v) for v in (0, 1, 5)]
_MAXS = [Max(v) for v in (10, 20)]
_LABELS = [Label(t) for t in ("a", "b")]
# Every Min is below every Max, so no shuffle can compile into an empty range
# and the property stays about layering rather than about cross-checks.
_ATOMS = _MINS + _MAXS + _LABELS

_LAYERS = st.lists(st.lists(st.sampled_from(_ATOMS), min_size=1, max_size=3),
                   min_size=1, max_size=3)


def _last(atoms, atom_cls):
    return next((a for a in reversed(atoms) if type(a) is atom_cls), None)


@settings(deadline=None, max_examples=300)
@given(layers=_LAYERS)
def test_layering_equals_flattening_and_the_last_atom_of_each_class_wins(layers):
    """docs/atoms.md, 'Layering': 'the outer layer wins; within one layer, the rightmost atom wins'.

    Nesting Annotated 1-3 deep with shuffled Min/Max/Label must compile to
    exactly the Field the single flat layer compiles to, whatever typing does to
    the spelling in between.
    """
    nested = int
    for layer in layers:
        nested = Annotated[tuple([nested, *layer])]

    flat_atoms = [atom for layer in layers for atom in layer]
    flat = Annotated[tuple([int, *flat_atoms])]

    nested_field = _field(nested)

    assert _summary(nested_field) == _summary(_field(flat))

    assert nested_field.shape == (Int(min=_last(flat_atoms, Min), max=_last(flat_atoms, Max)),)
    assert nested_field.label == _last(flat_atoms, Label)


@settings(deadline=None, max_examples=200)
@given(layers=_LAYERS)
def test_layering_survives_hoisting_out_of_an_optional_union(layers):
    """docs/atoms.md: hoisting out of `X | None` must not disturb the layering rule."""
    nested = int
    for layer in layers:
        nested = Annotated[tuple([nested, *layer])]

    flat_atoms = [atom for layer in layers for atom in layer]

    f = _field(nested | None)

    assert f.shape == (Int(min=_last(flat_atoms, Min), max=_last(flat_atoms, Max)), NoneShape())
    assert f.label == _last(flat_atoms, Label)

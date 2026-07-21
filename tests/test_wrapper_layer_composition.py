"""Where the `$type`/`$value` wrapper meets the mechanisms it is normally tested beside.

The wrapper of docs/build.md ("Other unions that share an input type") and the
inline `$type` of a dataclass union are each pinned on their own in
test_discriminated_wrapper.py and test_discriminator.py. This file pins their
*compositions*: a wrapped list whose items carry their own inline discriminator,
a dataclass option using `$value` as the separator against ambiguous lists, a
wrapped default served through a Signature, and the pickling of errors that
surface under `$value` at depth. docs/build.md: "Failures keep their
coordinates, including `$value` and the index below it".
"""

import pickle
from dataclasses import dataclass, make_dataclass

import pytest

from pytypehint import (
    SchemaTypeError, SchemaValueError, signature_of, struct_of,
)


@dataclass
class Shirt:
    size: str


@dataclass
class Mug:
    capacity: int


def _wrap(option, value):
    return {"$type": option, "$value": value}


# --------------------- wrapper selects a list of discriminated dataclasses ---
# `list[Shirt | Mug] | list[str]`: both options arrive as a list, so the wrapper
# names the list; only then does each item route by its own inline `$type`. Two
# discriminator layers stack in one value.


def _shirt_mug_or_str():
    return struct_of(make_dataclass("C", [("x", list[Shirt | Mug] | list[str])]))


def test_the_wrapper_selects_a_list_whose_items_carry_their_own_inline_discriminator():
    """docs/build.md: the wrapper "selects one option, and only then is `$value` validated" — here each `$value` item is itself a discriminated dataclass union.

    Regression caught: if the wrapper stopped re-entering item discrimination on
    its payload (treating `$value` as opaque), the inline `$type` on Shirt/Mug
    would go unconsumed and construction would fail.
    """
    schema = _shirt_mug_or_str()

    built = schema.build({"x": _wrap("list[Shirt | Mug]", [
        {"$type": "Shirt", "size": "M"},
        {"$type": "Mug", "capacity": 3},
    ])})

    assert built.x == [Shirt("M"), Mug(3)]


def test_the_wrapper_can_also_select_the_plain_list_arm():
    """docs/restrictions.md, 'Option identity': `list[str]` is a distinct identity from `list[Shirt | Mug]`.

    Regression caught: a bug conflating the two list arms' identities would make
    the wrong arm win here.
    """
    schema = _shirt_mug_or_str()

    assert schema.build({"x": _wrap("list[str]", ["a", "b"])}).x == ["a", "b"]


def test_resolve_preserves_both_the_wrapper_and_the_inline_discriminators():
    """docs/resolve.md: "resolve returns the wrapper as it was given" — and the inline `$type` inside `$value` survives too.

    Regression caught: any stripping of `$type` during resolve (build's job, not
    resolve's) would change the returned tree.
    """
    schema = _shirt_mug_or_str()
    data = {"x": _wrap("list[Shirt | Mug]", [
        {"$type": "Mug", "capacity": 3},
    ])}

    assert schema.resolve(data) == data


def test_a_bad_inline_discriminator_reports_through_value_index_and_type():
    """docs/build.md: "Failures keep their coordinates, including `$value` and the index below it" — and the inline `$type` below that.

    Regression caught: dropping any of the four segments would collapse the path
    a wrapper needs to point at the exact offending discriminator.
    """
    schema = _shirt_mug_or_str()

    with pytest.raises(SchemaValueError) as error:
        schema.build({"x": _wrap("list[Shirt | Mug]", [
            {"$type": "Shirt", "size": "M"},
            {"$type": "Other", "capacity": 3},
        ])})

    assert error.value.path == ("x", "$value", 1, "$type")
    assert str(error.value) == (
        "x: $value: [1]: $type: not a choice: 'Other', "
        "expected one of ('Shirt', 'Mug')")


def test_a_bad_item_field_reports_through_value_index_and_field():
    """docs/build.md: "the index below it" continues into the item's own field coordinate.

    Regression caught: a wrapper payload that skipped per-item field validation
    would let `capacity="x"` through, or would report it without the full path.
    """
    schema = _shirt_mug_or_str()

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": _wrap("list[Shirt | Mug]", [
            {"$type": "Mug", "capacity": "x"},
        ])})

    assert error.value.path == ("x", "$value", 0, "capacity")
    assert str(error.value) == "x: $value: [0]: capacity: expected int, got str"


def test_a_missing_inline_discriminator_under_the_wrapper_names_the_variants():
    """docs/build.md: 'ambiguous dict: field accepts File | Url — add "$type" naming the variant' — raised here one level under `$value`.

    Regression caught: if the wrapper validated its payload without re-entering
    dataclass-union discrimination, a `$type`-less item would be silently
    accepted instead of reported as ambiguous.
    """
    schema = _shirt_mug_or_str()

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": _wrap("list[Shirt | Mug]", [{"size": "M"}])})

    assert error.value.path == ("x", "$value", 0)
    assert str(error.value) == (
        'x: $value: [0]: ambiguous dict: field accepts Shirt | Mug '
        '— add "$type" naming the variant')


# --------------------- a dataclass option and ambiguous lists: `$value` splits ---
# `Shirt | list[str] | list[int]`. A dict is a Shirt payload unless it carries
# the reserved `$value` key, in which case it is a wrapper — and the wrapper only
# offers the two *ambiguous* identities, never the dataclass neighbour.


def _shirt_or_ambiguous_lists():
    return struct_of(make_dataclass("C", [("x", Shirt | list[str] | list[int])]))


def test_the_reserved_value_key_routes_a_dict_to_the_wrapper_not_the_dataclass():
    """docs/build.md: "the reserved `$value` key tells the two dictionary formats apart".

    Regression caught: if `$value` stopped being the separator, a wrapper dict
    would be misread as a Shirt payload (missing 'size'), or a Shirt payload
    would be misread as a wrapper.
    """
    schema = _shirt_or_ambiguous_lists()

    assert schema.build({"x": {"size": "M"}}).x == Shirt("M")
    assert schema.build({"x": _wrap("list[int]", [1])}).x == [1]


def test_a_wrapper_naming_a_dataclass_neighbour_is_not_a_choice():
    """docs/build.md: the wrapper carries an *option identity* — a dataclass routes inline, so its name is not among the wrapper's choices.

    Regression caught: if the dataclass identity leaked into the wrapper's name
    set, `$type: "Shirt"` inside a `$value` wrapper would be wrongly accepted.
    """
    schema = _shirt_or_ambiguous_lists()

    with pytest.raises(SchemaValueError) as error:
        schema.resolve({"x": _wrap("Shirt", [1])})

    assert error.value.path == ("x", "$type")
    assert error.value.leaf == (
        "not a choice: 'Shirt', expected one of ('list[str]', 'list[int]')")


def test_a_value_dict_missing_its_type_names_only_the_wrapped_lists():
    """docs/build.md: a `$value` dict without `$type` reports as an ambiguous wrapper, offering only the identities the wrapper actually holds.

    Regression caught: including the dataclass Shirt in this offer would misstate
    the way out to the caller.
    """
    schema = _shirt_or_ambiguous_lists()

    with pytest.raises(SchemaTypeError) as error:
        schema.resolve({"x": {"$value": [1]}})

    assert error.value.leaf == (
        'ambiguous value: field accepts list[str] | list[int] — wrap it as '
        '{"$type": ..., "$value": ...} naming the option')


# ------------------------------------- errors under `$value` survive pickling ---
# test_errors_pickle.py round-trips paths like ("page","size") and ("tags",1);
# test_discriminated_wrapper.py round-trips only a `$type` error at ("x","$type").
# Neither pickles an error whose path descends *below* `$value`.


def test_a_deep_value_index_error_survives_pickling():
    """docs/errors (errors.py): `__reduce__` "Rebuild[s] from the real arguments" — a path threading `$value` and two list indexes must round-trip intact.

    Regression caught: a __reduce__ that rebuilt from the rendered `args` line
    would revive leaf=<whole line>, path=(), losing the ("x","$value",1,1) path.
    """
    schema = struct_of(make_dataclass("D", [("x", list[list[str]] | list[list[int]])]))

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": _wrap("list[list[int]]", [[1], [2, "3"]])})

    assert error.value.path == ("x", "$value", 1, 1)

    revived = pickle.loads(pickle.dumps(error.value))
    assert type(revived) is SchemaTypeError
    assert revived.path == ("x", "$value", 1, 1)
    assert revived.leaf == error.value.leaf
    assert str(revived) == "x: $value: [1]: [1]: expected int, got str"


def test_an_inline_type_error_under_value_survives_pickling():
    """docs/build.md: an inline discriminator under `$value` is "its own coordinate" — and that coordinate must survive a pickle round-trip.

    Regression caught: as above, but for a `$type` segment nested under `$value`,
    which a args-based reduce would also flatten away.
    """
    schema = _shirt_mug_or_str()

    with pytest.raises(SchemaValueError) as error:
        schema.build({"x": _wrap("list[Shirt | Mug]", [
            {"$type": "Shirt", "size": "M"},
            {"$type": "Other", "capacity": 3},
        ])})

    revived = pickle.loads(pickle.dumps(error.value))
    assert type(revived) is SchemaValueError
    assert revived.path == ("x", "$value", 1, "$type")
    assert str(revived) == str(error.value)


# ------------------------------- a wrapped default served through a Signature ---
# test_discriminated_wrapper.py::test_a_signature_parameter_takes_the_wrapper_too
# supplies the wrapped argument. Here the wrapped parameter has a *default* and is
# *omitted*, so the default recipe is served — then the wrapper is supplied too.


def test_a_signature_parameter_serves_an_ambiguous_list_default_then_takes_the_wrapper():
    """docs/defaults.md: "a default is a value, not input data ... it needs no discriminator" — a Signature parameter serves it fresh when omitted, and still accepts the wrapper when supplied.

    Regression caught: if _resolve_fields routed the served default (a bare list)
    through the wrapper path meant for input dicts, the omitted case would raise
    'ambiguous list' instead of serving ["a", "b"].
    """
    def run(terms: list[str] | list[int] = ["a", "b"], n: int = 1):
        return terms, n

    sig = signature_of(run)

    assert sig.build({}) == {"terms": ["a", "b"], "n": 1}
    assert sig.resolve({}) == {"terms": ["a", "b"], "n": 1}
    assert sig.build({"terms": _wrap("list[int]", [1, 2])}) == {"terms": [1, 2], "n": 1}


def test_a_signature_serves_an_ambiguous_list_default_fresh_per_call():
    """docs/defaults.md: "the empty list is served fresh per missing key" — through the Signature path as well.

    Regression caught: a Signature default cached instead of rematerialized would
    share one list across calls.
    """
    def run(terms: list[str] | list[int] = []):
        return terms

    sig = signature_of(run)
    first = sig.build({})["terms"]
    second = sig.build({})["terms"]

    assert first == second == []
    assert first is not second


def test_a_signature_parameter_serves_a_dataclass_union_default_then_takes_type():
    """docs/build.md: a dataclass union "requires the reserved `$type` key" for input, while its default is a reconstructed instance served on omission.

    Regression caught: if the omitted dataclass-union default were forced through
    the `$type` input contract, the fresh File() serving would raise 'ambiguous
    dict' instead of being served.
    """
    def run(src: Shirt | Mug = Shirt("M"), n: int = 1):
        return src, n

    sig = signature_of(run)

    assert sig.build({}) == {"src": Shirt("M"), "n": 1}
    assert sig.build({"src": {"$type": "Mug", "capacity": 3}}) == {"src": Mug(3), "n": 1}

"""The scalar rows of the option-identity table, and their use as a wrapper `$type`.

docs/restrictions.md, 'Option identity', lists the scalar identities as
"its type name: `int`, `float`, `str`, `bool`, `date`, `time`". The existing
contract test (test_documentation_contract.py::
test_option_identity_matches_the_documented_table) pins only `int`, `str`,
`None`, an enum and several `List` forms — `bool`, `float`, `date` and `time`
are documented but untested. This file pins those four, and then exercises them
as real discriminators: they surface as `$type` strings through `List.option_id`
inside the `$type`/`$value` wrapper.
"""

from datetime import date, time

from dataclasses import make_dataclass

import pytest

from pytypehint import Bool, Date, Float, Time, struct_of


@pytest.mark.parametrize("shape, option_id", [
    (Bool(), "bool"),
    (Float(), "float"),
    (Date(), "date"),
    (Time(), "time"),
])
def test_scalar_option_id_matches_the_documented_table(shape, option_id):
    """docs/restrictions.md, 'Option identity': scalar identity is "its type name" — including bool, float, date and time.

    Regression caught: any of these shapes returning something other than its
    bare `pytype.__name__` (e.g. a qualified or prefixed name) would break the
    identity a discriminator prints, undetected by the existing table test.
    """
    assert shape.option_id() == option_id


def _compile(hint):
    return struct_of(make_dataclass("C", [("x", hint)]))


def _wrap(option, value):
    return {"$type": option, "$value": value}


def test_bool_and_float_identities_are_the_wrapper_discriminator():
    """docs/build.md: the wrapper's `$type` is the "option identity" — a `list[bool]`/`list[float]` tie is broken by exactly those names.

    Regression caught: if List.option_id spelled its bool/float item with a
    different token, the wrapper here would reject a correct `$type`.
    """
    schema = _compile(list[bool] | list[float])

    assert [s.option_id() for s in schema.fields[0].shape] == ["list[bool]", "list[float]"]
    assert schema.build({"x": _wrap("list[bool]", [True, False])}).x == [True, False]
    assert schema.build({"x": _wrap("list[float]", [1.5])}).x == [1.5]


def test_date_and_time_identities_are_the_wrapper_discriminator():
    """docs/build.md: the same wrapper contract carries `list[date]` / `list[time]` identities.

    Regression caught: a temporal item whose identity token drifted would make
    the `$type` here unroutable even though the schema compiled.
    """
    schema = _compile(list[date] | list[time])

    assert [s.option_id() for s in schema.fields[0].shape] == ["list[date]", "list[time]"]
    assert schema.build({"x": _wrap("list[date]", [date(2020, 1, 1)])}).x == [date(2020, 1, 1)]
    assert schema.build({"x": _wrap("list[time]", [time(12, 0)])}).x == [time(12, 0)]


def test_an_unknown_choice_names_the_scalar_list_identities():
    """docs/build.md: "not a choice: ..., expected one of (...)" lists the exact identities the wrapper offers.

    Regression caught: a change to how bool/float identities render would show up
    verbatim in this offer, so the message pins them character for character.
    """
    schema = _compile(list[bool] | list[float])

    with pytest.raises(ValueError) as error:
        schema.resolve({"x": _wrap("list[int]", [])})

    assert error.value.path == ("x", "$type")
    assert error.value.leaf == (
        "not a choice: 'list[int]', expected one of ('list[bool]', 'list[float]')")

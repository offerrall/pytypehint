"""`check_options_value` attaches a cause note per candidate on 'matches no option'.

src/pytypehint/validation.py: when several options share the value's runtime type
and none accepts it, the leaf names the options tried and a PEP 678 note records
why each rejected the value. The leaf and str() (first line) are unchanged; the
notes ride along and survive pickle, backing the claim errors.py makes that
add_note() survives its __reduce__.
"""

import pickle

import pytest

from pytypehint import Min, SchemaValueError
from pytypehint.shapes import Int, List, Str
from pytypehint.validation import check_options_value


# `["a", 1.5]` is a list, the runtime type both options share, but it satisfies
# neither list[str] (index 1 is a float) nor list[int] (index 0 is a str).
_SHAPES = (List(item=(Str(),)), List(item=(Int(),)))
_VALUE = ["a", 1.5]

_EXPECTED_NOTES = [
    "as list[str]: [1]: expected str, got float",
    "as list[int]: [0]: expected int, got str",
]


def _raise():
    with pytest.raises(SchemaValueError) as error:
        check_options_value(_SHAPES, _VALUE)
    return error.value


def test_the_main_message_is_unchanged():
    error = _raise()

    assert error.leaf == "matches no option: list[str] | list[int]"
    assert str(error) == "matches no option: list[str] | list[int]"
    assert error.path == ()


def test_each_candidate_contributes_a_cause_note():
    error = _raise()

    assert error.__notes__ == _EXPECTED_NOTES


def test_notes_survive_pickle():
    error = _raise()

    revived = pickle.loads(pickle.dumps(error))

    assert revived.__notes__ == _EXPECTED_NOTES
    assert revived.leaf == "matches no option: list[str] | list[int]"
    assert str(revived) == "matches no option: list[str] | list[int]"


def test_a_single_candidate_reports_its_own_violation_without_notes():
    # One candidate of the runtime type takes the direct path: its own leaf, no
    # "matches no option" and nothing to annotate.
    with pytest.raises(SchemaValueError) as error:
        check_options_value((Int(min=Min(0)),), -1)

    assert error.value.leaf == "too small: -1, minimum 0"
    assert not hasattr(error.value, "__notes__")

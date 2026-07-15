import pytest

from pytypehint.atoms import (
    Choices, Description, Label, Max, Min, MultipleOf, Placeholder, Slider, Step,
)


SINGLE_FIELD = [
    (Min, 0),
    (Max, 0),
    (Step, 1),
    (Label, "x"),
    (Description, "x"),
    (Placeholder, "x"),
]


@pytest.mark.parametrize("cls, value", SINGLE_FIELD, ids=[c.__name__ for c, _ in SINGLE_FIELD])
def test_single_field_atom_positional(cls, value):
    cls(value)


@pytest.mark.parametrize("cls, value", SINGLE_FIELD, ids=[c.__name__ for c, _ in SINGLE_FIELD])
def test_single_field_atom_keyword_still_works(cls, value):
    cls(value=value)


@pytest.mark.parametrize("cls, value", SINGLE_FIELD, ids=[c.__name__ for c, _ in SINGLE_FIELD])
def test_single_field_positional_equals_keyword(cls, value):
    assert cls(value) == cls(value=value)


def test_slider_rejects_positional():
    with pytest.raises(TypeError):
        Slider(True)


def test_slider_keyword_works():
    Slider()
    Slider(show_value=False)


def test_choices_rejects_positional():
    with pytest.raises(TypeError):
        Choices(1, 2, 3)


def test_choices_keyword_works():
    Choices(values=(1, 2, 3))


def test_choices_unhashable_values_raise_typeerror():
    with pytest.raises(TypeError, match=r"^Choices\.values must be hashable$"):
        Choices(values=([1],))


def test_choices_repeated_values_still_raise_valueerror():
    # the hashable guard must not swallow the repeat ValueError (except catches
    # TypeError only) — this stays exactly as before.
    with pytest.raises(ValueError, match=r"^Choices\.values must not repeat$"):
        Choices(values=(1, 1))


def test_min_rejects_bool():
    with pytest.raises(TypeError):
        Min(True)


def test_min_rejects_str():
    with pytest.raises(TypeError):
        Min("0")


def test_min_exclusive_defaults_false():
    assert Min(0).exclusive is False


def test_min_exclusive_true():
    assert Min(0, exclusive=True).exclusive is True


def test_min_exclusive_rejects_non_bool():
    with pytest.raises(TypeError, match="exclusive must be bool"):
        Min(0, exclusive="yes")


def test_min_exclusive_is_keyword_only():
    with pytest.raises(TypeError):
        Min(0, True)


def test_min_inclusive_not_equal_exclusive():
    assert Min(0) != Min(0, exclusive=True)


def test_multiple_of_rejects_zero():
    with pytest.raises(ValueError, match="must be > 0"):
        MultipleOf(0)


def test_multiple_of_rejects_negative():
    with pytest.raises(ValueError, match="must be > 0"):
        MultipleOf(-5)


def test_multiple_of_rejects_float():
    with pytest.raises(TypeError, match="must be int"):
        MultipleOf(2.5)


def test_multiple_of_rejects_bool():
    with pytest.raises(TypeError, match="must be int"):
        MultipleOf(True)


def test_multiple_of_equality():
    assert MultipleOf(5) == MultipleOf(5)
    assert MultipleOf(5) != MultipleOf(3)

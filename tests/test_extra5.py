import pytest

from pytypehint import Choices, Max, Min, MultipleOf
from pytypehint.shapes import Float, Int


INT_INCL = Int(min=Min(0), max=Max(10))
INT_EXCL = Int(min=Min(0, exclusive=True), max=Max(10, exclusive=True))
INT_MIN = Int(min=Min(5))
INT_MAX = Int(max=Max(5))


@pytest.mark.parametrize("v", list(range(0, 11)))
def test_int_inclusive_accepts_whole_range(v):
    INT_INCL._check(v)


@pytest.mark.parametrize("v", [-100, -10, -1, 11, 12, 50, 1000])
def test_int_inclusive_rejects_outside(v):
    with pytest.raises(ValueError):
        INT_INCL._check(v)


@pytest.mark.parametrize("v", list(range(1, 10)))
def test_int_exclusive_accepts_interior(v):
    INT_EXCL._check(v)


@pytest.mark.parametrize("v", [-1, 0, 10, 11])
def test_int_exclusive_rejects_ends_and_outside(v):
    with pytest.raises(ValueError):
        INT_EXCL._check(v)


@pytest.mark.parametrize("v", [5, 6, 100, 10_000])
def test_int_min_only_accepts_at_or_above(v):
    INT_MIN._check(v)


@pytest.mark.parametrize("v", [4, 0, -1, -100])
def test_int_min_only_rejects_below(v):
    with pytest.raises(ValueError, match="too small"):
        INT_MIN._check(v)


@pytest.mark.parametrize("v", [5, 4, 0, -100])
def test_int_max_only_accepts_at_or_below(v):
    INT_MAX._check(v)


@pytest.mark.parametrize("v", [6, 7, 100, 10_000])
def test_int_max_only_rejects_above(v):
    with pytest.raises(ValueError, match="too large"):
        INT_MAX._check(v)


MULT3 = Int(multiple_of=MultipleOf(3))


@pytest.mark.parametrize("v", [-9, -3, 0, 3, 6, 9, 30, 300])
def test_int_multiple_of_accepts(v):
    MULT3._check(v)


@pytest.mark.parametrize("v", [1, 2, 4, 5, 7, 8, 10, 100, -1, -2])
def test_int_multiple_of_rejects(v):
    with pytest.raises(ValueError, match="not a multiple"):
        MULT3._check(v)


CHOICE_INT = Int(choices=Choices(values=(2, 4, 8, 16)))


@pytest.mark.parametrize("v", [2, 4, 8, 16])
def test_int_choices_accepts_members(v):
    CHOICE_INT._check(v)


@pytest.mark.parametrize("v", [0, 1, 3, 5, 7, 9, 15, 17, 32])
def test_int_choices_rejects_non_members(v):
    with pytest.raises(ValueError, match="not a choice"):
        CHOICE_INT._check(v)


FLOAT_INCL = Float(min=Min(0.0), max=Max(1.0))
FLOAT_EXCL = Float(min=Min(0.0, exclusive=True), max=Max(1.0, exclusive=True))


@pytest.mark.parametrize("v", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_float_inclusive_accepts(v):
    FLOAT_INCL._check(v)


@pytest.mark.parametrize("v", [-0.1, -1.0, 1.1, 2.0, 100.0])
def test_float_inclusive_rejects_outside(v):
    with pytest.raises(ValueError):
        FLOAT_INCL._check(v)


@pytest.mark.parametrize("v", [0.01, 0.5, 0.99])
def test_float_exclusive_accepts_interior(v):
    FLOAT_EXCL._check(v)


@pytest.mark.parametrize("v", [0.0, 1.0, -0.1, 1.1])
def test_float_exclusive_rejects_ends(v):
    with pytest.raises(ValueError):
        FLOAT_EXCL._check(v)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_float_non_finite_always_rejected(bad):
    with pytest.raises(ValueError, match="not finite"):
        Float()._check(bad)


NEG_RANGE = Int(min=Min(-10), max=Max(-1))


@pytest.mark.parametrize("v", list(range(-10, 0)))
def test_int_negative_range_accepts(v):
    NEG_RANGE._check(v)


@pytest.mark.parametrize("v", [-11, -20, 0, 1, 5])
def test_int_negative_range_rejects(v):
    with pytest.raises(ValueError):
        NEG_RANGE._check(v)


NEG_MULT = Int(multiple_of=MultipleOf(4))


@pytest.mark.parametrize("v", [-16, -12, -8, -4, 0, 4, 8, 100, 400])
def test_int_multiple_of_accepts_negatives_and_zero(v):
    NEG_MULT._check(v)


@pytest.mark.parametrize("v", [-15, -13, -1, 1, 2, 3, 5, 6, 7])
def test_int_multiple_of_rejects_non_multiples(v):
    with pytest.raises(ValueError, match="not a multiple"):
        NEG_MULT._check(v)


COMBINED = Int(min=Min(0), max=Max(100), multiple_of=MultipleOf(10))


@pytest.mark.parametrize("v", [0, 10, 20, 50, 90, 100])
def test_int_combined_constraints_accept(v):
    COMBINED._check(v)


@pytest.mark.parametrize("v,why", [
    (-10, "too small"),
    (110, "too large"),
    (15, "not a multiple"),
    (5, "not a multiple"),
])
def test_int_combined_constraints_reject(v, why):
    with pytest.raises(ValueError, match=why):
        COMBINED._check(v)


@pytest.mark.parametrize("v", [10 ** 18, 2 ** 63, -(2 ** 63), 10 ** 40])
def test_int_accepts_huge_values(v):
    Int()._check(v)


CHOICE_STEP = Int(min=Min(0), max=Max(50), choices=Choices(values=(0, 25, 50)))


@pytest.mark.parametrize("v", [0, 25, 50])
def test_int_choices_within_bounds_accept(v):
    CHOICE_STEP._check(v)


@pytest.mark.parametrize("v", [10, 30, 26, 24])
def test_int_choices_within_bounds_reject_non_choice(v):
    with pytest.raises(ValueError, match="not a choice"):
        CHOICE_STEP._check(v)


FLOAT_CHOICES = Float(choices=Choices(values=(0.1, 0.2, 0.3)))


@pytest.mark.parametrize("v", [0.1, 0.2, 0.3])
def test_float_choices_accept(v):
    FLOAT_CHOICES._check(v)


@pytest.mark.parametrize("v", [0.0, 0.15, 0.4, 1.0])
def test_float_choices_reject(v):
    with pytest.raises(ValueError, match="not a choice"):
        FLOAT_CHOICES._check(v)


@pytest.mark.parametrize("v", [-1e300, -1.0, 0.0, 1.0, 1e300])
def test_float_accepts_wide_finite_range(v):
    Float()._check(v)


FLOAT_NEG = Float(min=Min(-1.0), max=Max(1.0))


@pytest.mark.parametrize("v", [-1.0, -0.9, -0.001, 0.0, 0.001, 0.9, 1.0])
def test_float_symmetric_range_accepts(v):
    FLOAT_NEG._check(v)


@pytest.mark.parametrize("v", [-1.0001, 1.0001, -2.0, 2.0])
def test_float_symmetric_range_rejects(v):
    with pytest.raises(ValueError):
        FLOAT_NEG._check(v)

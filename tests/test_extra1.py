from datetime import date, time

import pytest

from pytypehint import (
    Choices, Description, IsPassword, IsPathFile, Label, Max, Min, MultipleOf,
    Pattern, Placeholder, Rows, Slider, Step,
)


def test_min_exclusive_must_be_bool():
    with pytest.raises(TypeError, match="Min.exclusive must be bool"):
        Min(0, exclusive=1)


def test_max_exclusive_must_be_bool():
    with pytest.raises(TypeError, match="Max.exclusive must be bool"):
        Max(0, exclusive=1)


def test_min_exclusive_none_rejected():
    with pytest.raises(TypeError, match="Min.exclusive must be bool"):
        Min(0, exclusive=None)


def test_label_value_must_be_str():
    with pytest.raises(TypeError, match="Label.value must be str"):
        Label(5)


def test_label_value_must_not_be_empty():
    with pytest.raises(ValueError, match="Label.value must not be empty"):
        Label("")


def test_description_value_must_be_str():
    with pytest.raises(TypeError, match="Description.value must be str"):
        Description(5)


def test_description_value_must_not_be_empty():
    with pytest.raises(ValueError, match="Description.value must not be empty"):
        Description("")


def test_pattern_value_must_be_str():
    with pytest.raises(TypeError, match="Pattern.value must be str"):
        Pattern(5)


def test_pattern_message_must_be_str():
    with pytest.raises(TypeError, match="Pattern.message must be str"):
        Pattern("x", message=5)


def test_pattern_message_must_not_be_empty():
    with pytest.raises(ValueError, match="Pattern.message must not be empty"):
        Pattern("x", message="")


def test_is_path_file_extensions_must_be_tuple():
    with pytest.raises(TypeError, match="IsPathFile.extensions must be tuple"):
        IsPathFile(extensions=[".png"])


def test_rows_value_must_be_int():
    with pytest.raises(TypeError, match="Rows.value must be int"):
        Rows(1.5)


def test_step_value_must_be_positive():
    with pytest.raises(ValueError, match="Step.value must be > 0"):
        Step(-1)


def test_choices_cross_type_is_not_a_repeat():
    # 1 and True (and 1 and 1.0) are distinct types, so not a repeat — the mix
    # is a shape concern, not "must not repeat".
    Choices(values=(1, True))
    Choices(values=(1, 1.0))
    with pytest.raises(ValueError, match="Choices.values must not repeat"):
        Choices(values=(1, 1))


@pytest.mark.parametrize("bad", [b"x", 1j, [1], {1}, {"a": 1}, None, "s"])
def test_min_rejects_non_orderable_values(bad):
    with pytest.raises(TypeError, match="must be orderable"):
        Min(bad)


@pytest.mark.parametrize("bad", [b"x", 1j, [1], {1}, {"a": 1}, None, "s"])
def test_max_rejects_non_orderable_values(bad):
    with pytest.raises(TypeError, match="must be orderable"):
        Max(bad)


@pytest.mark.parametrize("good", [0, -5, 3.14, date(2020, 1, 1), time(9, 0)])
def test_min_accepts_orderable_values(good):
    Min(good)
    Max(good)


@pytest.mark.parametrize("bad,msg", [
    (0, "must be > 0"),
    (-1, "must be > 0"),
    (-99, "must be > 0"),
    (1.5, "must be int"),
    (2.0, "must be int"),
    (True, "must be int"),
    ("3", "must be int"),
])
def test_multiple_of_invalid(bad, msg):
    with pytest.raises((TypeError, ValueError), match=msg):
        MultipleOf(bad)


@pytest.mark.parametrize("good", [1, 2, 3, 100, 10 ** 9])
def test_multiple_of_valid(good):
    MultipleOf(good)


@pytest.mark.parametrize("bad,msg", [
    (0, "must be > 0"),
    (-1, "must be > 0"),
    (1.5, "must be int"),
    (True, "must be int"),
])
def test_rows_invalid(bad, msg):
    with pytest.raises((TypeError, ValueError), match=msg):
        Rows(bad)


@pytest.mark.parametrize("bad,msg", [
    (0, "must be > 0"),
    (-1, "must be > 0"),
    (-0.5, "must be > 0"),
    (True, "must be a number"),
    ("1", "must be a number"),
    (None, "must be a number"),
])
def test_step_invalid(bad, msg):
    with pytest.raises((TypeError, ValueError), match=msg):
        Step(bad)


@pytest.mark.parametrize("good", [1, 2, 100, 0.1, 0.5, 2.5])
def test_step_valid(good):
    Step(good)


@pytest.mark.parametrize("bad", ["(", "[a-", "*abc", "(?P<n>", "a{2,1}", "(?"])
def test_pattern_invalid_regex(bad):
    with pytest.raises(ValueError, match="is not a valid regex"):
        Pattern(bad)


@pytest.mark.parametrize("good", [r"\d+", r"[a-z]+", r"^x$", r"(a|b)*", r".+"])
def test_pattern_valid_regex(good):
    Pattern(good)
    Pattern(good, message="custom")


@pytest.mark.parametrize("exts,msg", [
    (("png",), "must start with '.'"),
    ((".PNG",), "must be lowercase"),
    ((".Png",), "must be lowercase"),
    ((".png", ".png"), "must not repeat"),
    ((5,), "expected str"),
    ((".png", 3), "expected str"),
])
def test_is_path_file_invalid_extensions(exts, msg):
    with pytest.raises((TypeError, ValueError), match=msg):
        IsPathFile(extensions=exts)


@pytest.mark.parametrize("exts", [(), (".png",), (".png", ".jpg", ".webp"), (".tar.gz",)])
def test_is_path_file_valid_extensions(exts):
    IsPathFile(extensions=exts)


@pytest.mark.parametrize("bad", [1, "yes", None, 0])
def test_slider_show_value_must_be_bool(bad):
    with pytest.raises(TypeError, match="show_value must be bool"):
        Slider(show_value=bad)


def test_slider_valid():
    Slider()
    Slider(show_value=True)
    Slider(show_value=False)


@pytest.mark.parametrize("bad", [5, None, b"x", 1.0])
def test_placeholder_must_be_str(bad):
    with pytest.raises(TypeError, match="Placeholder.value must be str"):
        Placeholder(bad)


@pytest.mark.parametrize("text", ["pick", "choose one", "  "])
def test_placeholder_valid(text):
    Placeholder(text)


@pytest.mark.parametrize("values", [(1,), (1, 2, 3), ("a", "b"), (1.0, 2.0), (True, False)])
def test_choices_valid_tuples(values):
    Choices(values=values)


def test_is_password_takes_no_args():
    IsPassword()


@pytest.mark.parametrize("text", ["x", "Label text", "a"])
def test_label_and_description_valid(text):
    Label(text)
    Description(text)


@pytest.mark.parametrize("flag", [1, 0, None, "no"])
def test_min_max_exclusive_flag_variants_rejected(flag):
    with pytest.raises(TypeError, match="exclusive must be bool"):
        Min(0, exclusive=flag)
    with pytest.raises(TypeError, match="exclusive must be bool"):
        Max(0, exclusive=flag)

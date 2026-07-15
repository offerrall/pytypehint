from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated

import pytest

from pytypehint.atoms import (
    Choices, IsPassword, IsPathFile, Max, Min, MultipleOf, Pattern,
    Placeholder, Rows, Slider, Step,
)
from pytypehint.bridge import struct_of
from pytypehint.shapes import Int, List, NoneShape, Str


def test_pattern_rejects_invalid_regex():
    with pytest.raises(ValueError, match="not a valid regex"):
        Pattern("[")


def test_pattern_rejects_empty():
    with pytest.raises(ValueError, match="must not be empty"):
        Pattern("")


def test_pattern_rejects_empty_message():
    with pytest.raises(ValueError, match="must not be empty"):
        Pattern("x", message="")


def test_pattern_rejects_non_str_message():
    with pytest.raises(TypeError, match="message must be str"):
        Pattern("x", message=5)


def test_rows_rejects_zero():
    with pytest.raises(ValueError, match="must be > 0"):
        Rows(0)


def test_rows_rejects_negative():
    with pytest.raises(ValueError, match="must be > 0"):
        Rows(-1)


def test_rows_rejects_float():
    with pytest.raises(TypeError, match="must be int"):
        Rows(2.5)


def test_is_path_file_extension_must_start_with_dot():
    with pytest.raises(ValueError, match="must start with"):
        IsPathFile(extensions=("png",))


def test_is_path_file_extension_must_be_lowercase():
    with pytest.raises(ValueError, match="must be lowercase"):
        IsPathFile(extensions=(".PNG",))


def test_is_path_file_extension_must_not_repeat():
    with pytest.raises(ValueError, match="must not repeat"):
        IsPathFile(extensions=(".png", ".png"))


def test_is_path_file_extension_must_be_str():
    with pytest.raises(TypeError, match="expected str"):
        IsPathFile(extensions=(1,))


def test_check_empty_string_valid():
    Str()._check("")


def test_check_string_valid():
    Str()._check("x")


def test_check_rejects_int():
    with pytest.raises(TypeError, match="expected str, got int"):
        Str()._check(1)


def test_check_rejects_bool():
    with pytest.raises(TypeError, match="expected str, got bool"):
        Str()._check(True)


def test_check_rejects_str_subclass():
    class S(str):
        pass

    with pytest.raises(TypeError, match="expected str"):
        Str()._check(S("x"))


def test_check_rejects_str_enum_member():
    class Color(StrEnum):
        RED = "red"

    with pytest.raises(TypeError, match="expected str"):
        Str()._check(Color.RED)


def test_min_length_too_short():
    with pytest.raises(ValueError, match="too short: 2 chars"):
        Str(min=Min(3))._check("ab")


def test_min_length_boundary_passes():
    Str(min=Min(3))._check("abc")


def test_max_length_too_long():
    with pytest.raises(ValueError, match="too long"):
        Str(max=Max(2))._check("abc")


def test_min_one_rejects_empty():
    with pytest.raises(ValueError, match="too short"):
        Str(min=Min(1))._check("")


def test_exclusive_length_rejected():
    with pytest.raises(ValueError, match="not supported for lengths"):
        Str(min=Min(0, exclusive=True))


def test_negative_length_rejected():
    with pytest.raises(ValueError, match="must be >= 0"):
        Str(min=Min(-1))


def test_empty_length_range():
    with pytest.raises(ValueError, match="empty range"):
        Str(min=Min(3), max=Max(2))


def test_pattern_fullmatch_passes():
    Str(pattern=Pattern(r"[0-9]+"))._check("123")


def test_pattern_fullmatch_rejects_partial():
    with pytest.raises(ValueError, match="does not match pattern"):
        Str(pattern=Pattern(r"[0-9]+"))._check("12a")


def test_pattern_custom_message():
    with pytest.raises(ValueError) as exc:
        Str(pattern=Pattern(r"[0-9]+", message="digits only"))._check("12a")
    assert str(exc.value) == "digits only"


def test_is_path_file_empty_extensions_no_limit():
    Str(is_path_file=IsPathFile())._check("anything")


def test_is_path_file_matching_extension():
    Str(is_path_file=IsPathFile(extensions=(".csv",)))._check("data.csv")


def test_is_path_file_case_insensitive():
    Str(is_path_file=IsPathFile(extensions=(".csv",)))._check("data.CSV")


def test_is_path_file_wrong_extension():
    with pytest.raises(ValueError, match="not an accepted file type"):
        Str(is_path_file=IsPathFile(extensions=(".csv",)))._check("data.json")


def test_choices_membership():
    Str(choices=Choices(values=("a", "b")))._check("a")
    with pytest.raises(ValueError, match="not a choice"):
        Str(choices=Choices(values=("a", "b")))._check("c")


def test_choices_reject_non_str():
    with pytest.raises(TypeError, match="expected str"):
        Str(choices=Choices(values=(1,)))


def test_choices_respect_min_length():
    with pytest.raises(ValueError, match="shorter than minimum"):
        Str(choices=Choices(values=("ab",)), min=Min(3))


def test_choices_respect_pattern():
    with pytest.raises(ValueError, match="does not match pattern"):
        Str(choices=Choices(values=("x1",)), pattern=Pattern(r"[a-z]+"))


def test_choices_respect_path_file():
    with pytest.raises(ValueError, match="not an accepted file type"):
        Str(choices=Choices(values=("a.txt",)), is_path_file=IsPathFile(extensions=(".csv",)))


def test_notation_is_inert():
    Str(is_password=IsPassword(), rows=Rows(5), placeholder=Placeholder("x"))._check("anything")


def test_bridge_str_end_to_end():
    @dataclass
    class C:
        s: Annotated[str, Min(1), Max(10), Pattern(r"[a-z]+")] = "x"

    schema = struct_of(C)
    assert schema.resolve({"s": "abc"}) == {"s": "abc"}
    with pytest.raises(ValueError, match="too short"):
        schema.resolve({"s": ""})
    with pytest.raises(ValueError, match="does not match pattern"):
        schema.resolve({"s": "ABC"})
    with pytest.raises(TypeError, match="expected str, got int"):
        schema.resolve({"s": 1})


def test_bridge_email_alias_custom_message_chains_field():
    Email = Annotated[str, Pattern(r"[^@]+@[^@]+", message="bad email")]

    @dataclass
    class C:
        email: Email = "a@b"

    schema = struct_of(C)
    with pytest.raises(ValueError, match=r"email: bad email"):
        schema.resolve({"email": "nope"})


def test_bridge_image_file_alias():
    ImageFile = Annotated[str, IsPathFile(extensions=(".png", ".jpg"))]

    @dataclass
    class C:
        pic: ImageFile = "a.png"

    schema = struct_of(C)
    assert schema.resolve({"pic": "photo.JPG"}) == {"pic": "photo.JPG"}
    with pytest.raises(ValueError, match="not an accepted file type"):
        schema.resolve({"pic": "doc.pdf"})


def test_bridge_optional_str():
    @dataclass
    class C:
        s: str | None = None

    schema = struct_of(C)
    assert schema.fields[0].shape == (Str(), NoneShape())
    assert schema.resolve({"s": None}) == {"s": None}
    assert schema.resolve({"s": "x"}) == {"s": "x"}


def test_bridge_list_of_str():
    @dataclass
    class C:
        ss: list[str] = field(default_factory=list)

    schema = struct_of(C)
    assert schema.fields[0].shape == (List(item=(Str(),)),)
    with pytest.raises(TypeError, match="expected str, got int"):
        schema.resolve({"ss": [1]})
    assert schema.resolve({"ss": ["a"]}) == {"ss": ["a"]}


def test_bridge_str_or_int_union():
    @dataclass
    class C:
        v: str | int = ""

    schema = struct_of(C)
    assert schema.fields[0].shape == (Str(), Int())
    assert schema.resolve({"v": "1"}) == {"v": "1"}
    assert schema.resolve({"v": 1}) == {"v": 1}


def test_bridge_rejects_wrong_metadata_on_str():
    for atom in (Slider(), Step(1), MultipleOf(2)):
        @dataclass
        class C:
            s: Annotated[str, atom] = "x"

        with pytest.raises(TypeError, match="unsupported metadata"):
            struct_of(C)


def test_bridge_rejects_str_metadata_on_int():
    for atom in (Rows(3), IsPassword()):
        @dataclass
        class C:
            n: Annotated[int, atom] = 0

        with pytest.raises(TypeError, match="unsupported metadata"):
            struct_of(C)


def test_layered_override_replaces_pattern():
    Base = Annotated[str, Pattern(r"[a-z]+")]

    @dataclass
    class C:
        s: Annotated[Base, Pattern(r"[0-9]+")] = "5"

    shape = struct_of(C).fields[0].shape[0]
    assert shape.pattern == Pattern(r"[0-9]+")


def test_struct_str_default():
    @dataclass
    class C:
        name: Annotated[str, Min(1)] = "x"

    struct_of(C)


def test_struct_empty_default_fails():
    @dataclass
    class C:
        name: Annotated[str, Min(1)] = ""

    with pytest.raises(ValueError, match="too short"):
        struct_of(C)


def test_struct_int_default_on_str_fails():
    @dataclass
    class C:
        name: Annotated[str, Min(1)] = 1

    with pytest.raises(TypeError, match="expected str"):
        struct_of(C)

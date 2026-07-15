from dataclasses import dataclass, field
from typing import Annotated, Literal

import pytest

from pytypehint import Choices, IsPathFile, Max, Min, Pattern, struct_of
from pytypehint.shapes import Str


@dataclass
class Lit:
    x: Literal["red", "green", "blue"] = "red"


@pytest.mark.parametrize("v", ["red", "green", "blue"])
def test_literal_accepts_members(v):
    assert struct_of(Lit).resolve({"x": v}) == {"x": v}


@pytest.mark.parametrize("v", ["RED", "yellow", "", "red ", " blue"])
def test_literal_rejects_non_members(v):
    with pytest.raises(ValueError, match="not a choice"):
        struct_of(Lit).resolve({"x": v})


@pytest.mark.parametrize("v", [1, 1.0, True, None, ["red"]])
def test_literal_rejects_wrong_type(v):
    with pytest.raises(TypeError, match="expected str"):
        struct_of(Lit).resolve({"x": v})


@dataclass
class IntLit:
    x: Literal[1, 2, 3] = 1


@pytest.mark.parametrize("v", [1, 2, 3])
def test_int_literal_accepts(v):
    assert struct_of(IntLit).resolve({"x": v}) == {"x": v}


@pytest.mark.parametrize("v", [0, 4, -1, 10])
def test_int_literal_rejects_non_members(v):
    with pytest.raises(ValueError, match="not a choice"):
        struct_of(IntLit).resolve({"x": v})


LEN = Str(min=Min(2), max=Max(5))


@pytest.mark.parametrize("s", ["ab", "abc", "abcd", "abcde"])
def test_str_length_accepts_within(s):
    LEN._check(s)


@pytest.mark.parametrize("s", ["", "a", "abcdef", "abcdefghij"])
def test_str_length_rejects_outside(s):
    with pytest.raises(ValueError):
        LEN._check(s)


DIGITS = Str(pattern=Pattern(r"\d+"))


@pytest.mark.parametrize("s", ["0", "1", "42", "007", "123456789"])
def test_str_pattern_accepts_matches(s):
    DIGITS._check(s)


@pytest.mark.parametrize("s", ["", "a", "1a", "a1", "1 2", " 12", "12 "])
def test_str_pattern_rejects_non_matches(s):
    with pytest.raises(ValueError, match="does not match pattern"):
        DIGITS._check(s)


PATH = Str(is_path_file=IsPathFile(extensions=(".png", ".jpg")))


@pytest.mark.parametrize("s", ["a.png", "a.jpg", "A.PNG", "photo.JPG", "x.y.png"])
def test_path_accepts_valid_extensions_case_insensitive(s):
    PATH._check(s)


@pytest.mark.parametrize("s", ["a.gif", "a.txt", "a", "png", "a.png.txt", ""])
def test_path_rejects_wrong_extensions(s):
    with pytest.raises(ValueError, match="not an accepted file type"):
        PATH._check(s)


CUSTOM = Str(pattern=Pattern(r"[a-z]+", message="lowercase letters only"))


def test_pattern_custom_message_used():
    with pytest.raises(ValueError, match="lowercase letters only"):
        CUSTOM._check("ABC")


@dataclass
class Full:
    name: Annotated[str, Min(1), Max(20)] = "x"
    age: Annotated[int, Min(0), Max(150)] = 0
    email: Annotated[str, Pattern(r"[^@]+@[^@]+")] = "a@b"


@pytest.mark.parametrize("data,ok", [
    ({"name": "Ada", "age": 36, "email": "ada@site"}, True),
    ({"name": "", "age": 36, "email": "ada@site"}, False),
    ({"name": "Ada", "age": -1, "email": "ada@site"}, False),
    ({"name": "Ada", "age": 200, "email": "ada@site"}, False),
    ({"name": "Ada", "age": 36, "email": "not-an-email"}, False),
])
def test_end_to_end_record(data, ok):
    if ok:
        assert struct_of(Full).resolve(data) == data
    else:
        with pytest.raises((TypeError, ValueError)):
            struct_of(Full).resolve(data)


@pytest.mark.parametrize("missing", ["name", "age", "email"])
def test_end_to_end_defaults_fill_each_field(missing):
    data = {"name": "Ada", "age": 36, "email": "ada@site"}
    del data[missing]
    result = struct_of(Full).resolve(data)
    assert missing in result


# float choices use Annotated[float, Choices(...)] — Literal doesn't carry floats
@dataclass
class FloatChoices:
    x: Annotated[float, Choices(values=(1.5, 2.5, 3.5))] = 1.5


@pytest.mark.parametrize("v", [1.5, 2.5, 3.5])
def test_float_choices_accepts(v):
    assert struct_of(FloatChoices).resolve({"x": v}) == {"x": v}


@pytest.mark.parametrize("v", [1.0, 2.0, 4.5, 0.0])
def test_float_choices_rejects(v):
    with pytest.raises(ValueError, match="not a choice"):
        struct_of(FloatChoices).resolve({"x": v})


@pytest.mark.parametrize("v", [1, "1.5"])
def test_float_choices_rejects_wrong_type(v):
    with pytest.raises(TypeError, match="expected float"):
        struct_of(FloatChoices).resolve({"x": v})


def test_float_literal_rejected():
    @dataclass
    class C:
        x: Literal[0.5, 1.0] = 0.5

    with pytest.raises(TypeError, match="Literal values must be int or str, got float"):
        struct_of(C)


EXACT = Str(min=Min(5), max=Max(5))


@pytest.mark.parametrize("s", ["abcde", "12345", "     "])
def test_str_exact_length_accepts(s):
    EXACT._check(s)


@pytest.mark.parametrize("s", ["abcd", "abcdef", "", "a"])
def test_str_exact_length_rejects(s):
    with pytest.raises(ValueError):
        EXACT._check(s)


PHONE = Str(pattern=Pattern(r"\+?\d{7,15}"))


@pytest.mark.parametrize("s", ["1234567", "+15551234567", "999999999999999"])
def test_phone_pattern_accepts(s):
    PHONE._check(s)


@pytest.mark.parametrize("s", ["12345", "abc", "+", "123-456-7890", ""])
def test_phone_pattern_rejects(s):
    with pytest.raises(ValueError, match="does not match pattern"):
        PHONE._check(s)


HEX = Str(pattern=Pattern(r"#[0-9a-f]{6}"))


@pytest.mark.parametrize("s", ["#000000", "#ffffff", "#a1b2c3"])
def test_hex_color_accepts(s):
    HEX._check(s)


@pytest.mark.parametrize("s", ["#FFF", "000000", "#gggggg", "#12345"])
def test_hex_color_rejects(s):
    with pytest.raises(ValueError):
        HEX._check(s)


MULTI_EXT = Str(is_path_file=IsPathFile(extensions=(".png", ".jpg", ".jpeg", ".webp", ".gif")))


@pytest.mark.parametrize("s", ["a.png", "b.JPG", "c.jpeg", "d.WEBP", "e.gif", "photo.final.png"])
def test_multi_extension_accepts(s):
    MULTI_EXT._check(s)


@pytest.mark.parametrize("s", ["a.bmp", "a.tiff", "a.svg", "a", "a.png.zip"])
def test_multi_extension_rejects(s):
    with pytest.raises(ValueError, match="not an accepted file type"):
        MULTI_EXT._check(s)


@dataclass
class Profile:
    handle: Annotated[str, Min(3), Max(15), Pattern(r"[a-z0-9_]+")] = "user"
    score: Annotated[int, Min(0), Max(100)] = 0
    bio: str | None = None
    tags: list[str] = field(default_factory=list)


@pytest.mark.parametrize("data,ok", [
    ({"handle": "ada_dev", "score": 88, "bio": "hi", "tags": ["a", "b"]}, True),
    ({"handle": "ada_dev", "score": 88, "bio": None, "tags": []}, True),
    ({"handle": "AB", "score": 88, "bio": None, "tags": []}, False),
    ({"handle": "has space", "score": 0, "bio": None, "tags": []}, False),
    ({"handle": "ada", "score": 101, "bio": None, "tags": []}, False),
    ({"handle": "ada", "score": 0, "bio": 5, "tags": []}, False),
    ({"handle": "ada", "score": 0, "bio": None, "tags": [1]}, False),
])
def test_profile_end_to_end(data, ok):
    if ok:
        assert struct_of(Profile).resolve(data) == data
    else:
        with pytest.raises((TypeError, ValueError)):
            struct_of(Profile).resolve(data)


@pytest.mark.parametrize("n", range(3, 16))
def test_handle_length_boundaries(n):
    struct_of(Profile).resolve({"handle": "a" * n, "score": 0, "bio": None, "tags": []})

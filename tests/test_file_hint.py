"""The `FileHint` file contract: a description of a file, not an inspection of one.

The atom states which extensions the name may take and which sizes the file must
fall between. Only the extension is a fact about the text, so only the extension
is checked here; the sizes are declared, carried in the portable document, and
answered by the boundary that has the file in hand. Nothing in this module
touches the filesystem, because nothing in the core does: existence, size and
file-ness are answers about the world that can change between the check and the
use, and an answer that stale is not one the core is willing to give.

Every value that passes stays the exact `str` it arrived as.
"""

import os
import pathlib
from dataclasses import dataclass, field, make_dataclass
from pathlib import Path
from typing import Annotated

import pytest

from pytypehint import (
    Choices, FileHint, Max, Min, Pattern, SchemaValueError, signature_of,
    struct_of,
)
from pytypehint.shapes import Str


def _str_node(annotation) -> dict:
    """The portable node of a `str` field carrying `annotation`."""
    model = make_dataclass("Probe", [("value", annotation)])
    document = struct_of(model).to_dict()
    (probe,) = document["defs"]["structs"]["Probe"]["fields"]
    return probe["shape"][0]


# ------------------------------------------------------------ the extension


def test_accepted_extension_passes():
    shape = Str(file_hint=FileHint(extensions=(".png", ".jpg")))
    shape._check("a.png")
    shape._check("b.jpg")


def test_rejected_extension_reports_the_accepted_set():
    shape = Str(file_hint=FileHint(extensions=(".png", ".jpg")))

    with pytest.raises(SchemaValueError) as error:
        shape._check("image.gif")
    assert error.value.leaf == (
        "not an accepted file type: 'image.gif', "
        "expected one of ('.png', '.jpg')")


def test_the_extension_is_compared_in_lowercase_against_the_text():
    # The atom stores its extensions lowercase, so the value is lowered before the
    # comparison: a shouted name is the same file type as a quiet one.
    Str(file_hint=FileHint(extensions=(".png",)))._check("FOTO.PNG")
    Str(file_hint=FileHint(extensions=(".png",)))._check("Foto.Png")


def test_a_mark_without_extensions_accepts_any_name():
    """With nothing declared there is nothing about the text left to refuse."""
    shape = Str(file_hint=FileHint())
    shape._check("report.pdf")
    shape._check("no-extension-at-all")


# ---------------------------------------------- validation asks the world nothing


def test_a_value_with_the_right_extension_validates_without_the_file_existing():
    """The heart of the atom: it describes a file, it does not go looking for one."""
    Str(file_hint=FileHint(extensions=(".png",)))._check("nowhere/on/disk.png")


def test_declared_sizes_reject_nothing_during_validation():
    """`min_size` and `max_size` narrow the contract, never the values the core sees."""
    shape = Str(file_hint=FileHint(extensions=(".bin",), min_size=1024, max_size=2048))

    # No value could satisfy these bounds by its text alone, and none has to: the
    # bounds are for the boundary holding the bytes.
    shape._check("empty.bin")
    shape._check("enormous.bin")


def test_declared_sizes_travel_to_the_portable_document():
    node = _str_node(Annotated[str, FileHint(extensions=(".pdf",), min_size=1, max_size=1024)])

    assert node["file_hint"] == {
        "extensions": [".pdf"], "min_size": 1, "max_size": 1024}


def test_validation_never_consults_the_filesystem():
    """Certified by making every route to the filesystem explode under the check."""
    def refuse(*args, **kwargs):
        raise AssertionError("the core consulted the filesystem")

    with pytest.MonkeyPatch.context() as patch:
        for owner, name in ((pathlib.Path, "stat"), (pathlib.Path, "exists"),
                            (pathlib.Path, "is_file"), (os, "stat"),
                            (os.path, "exists"), (os.path, "isfile")):
            patch.setattr(owner, name, refuse)

        Str(file_hint=FileHint(extensions=(".png",), min_size=1))._check("image.png")

        with pytest.raises(SchemaValueError, match="not an accepted file type"):
            Str(file_hint=FileHint(extensions=(".png",)))._check("image.gif")


def test_a_name_the_filesystem_could_never_open_is_still_only_text():
    # An embedded null byte makes this path unopenable on every platform. There is
    # no inspection to fail any more, so the extension is the whole verdict.
    Str(file_hint=FileHint(extensions=(".png",)))._check("a\0b.png")

    with pytest.raises(SchemaValueError, match="not an accepted file type"):
        Str(file_hint=FileHint(extensions=(".png",)))._check("a\0b.gif")


def test_built_value_is_still_exactly_str():
    ImagePath = Annotated[str, FileHint(extensions=(".png",))]

    def process(image: ImagePath):
        return image

    kwargs = signature_of(process).build({"image": "image.png"})

    # No coercion to `Path`, and no normalization of the text either.
    assert kwargs["image"] == "image.png"
    assert type(kwargs["image"]) is str


# --------------------------------------------------- atom argument validation


@pytest.mark.parametrize("kwargs, message", [
    ({"min_size": True}, "FileHint.min_size must be int or None, got bool"),
    ({"max_size": False}, "FileHint.max_size must be int or None, got bool"),
    ({"min_size": 1.5}, "FileHint.min_size must be int or None, got float"),
    ({"max_size": 1.5}, "FileHint.max_size must be int or None, got float"),
    ({"min_size": "10"}, "FileHint.min_size must be int or None, got str"),
    ({"max_size": "10"}, "FileHint.max_size must be int or None, got str"),
])
def test_size_must_be_int_or_none(kwargs, message):
    with pytest.raises(TypeError) as error:
        FileHint(**kwargs)
    assert str(error.value) == message


@pytest.mark.parametrize("kwargs, message", [
    ({"min_size": -1}, "FileHint.min_size must be >= 0, got -1"),
    ({"max_size": -1}, "FileHint.max_size must be >= 0, got -1"),
])
def test_size_must_not_be_negative(kwargs, message):
    with pytest.raises(ValueError) as error:
        FileHint(**kwargs)
    assert str(error.value) == message


def test_min_size_may_not_exceed_max_size():
    with pytest.raises(ValueError) as error:
        FileHint(min_size=100, max_size=50)
    assert str(error.value) == "FileHint: min_size 100 exceeds max_size 50"


@pytest.mark.parametrize("size", [None, 0, 1, 1024, 5 * 1024 * 1024])
def test_valid_sizes_are_accepted_on_both_bounds(size):
    FileHint(min_size=size)
    FileHint(max_size=size)


def test_equal_bounds_are_valid():
    FileHint(min_size=10, max_size=10)


# ----------------------------------------------------------------- choices


def test_choices_accept_a_name_meeting_the_contract():
    shape = Str(choices=Choices(values=("default.png",)),
                file_hint=FileHint(extensions=(".png",), max_size=1_000_000))
    shape._check("default.png")


def test_choices_reject_a_wrong_extension():
    with pytest.raises(ValueError) as error:
        Str(choices=Choices(values=("notes.txt",)),
            file_hint=FileHint(extensions=(".png",)))
    assert str(error.value) == (
        "Str.choices: not an accepted file type: 'notes.txt', "
        "expected one of ('.png',)")


def test_choices_are_certified_through_compilation():
    """A choice that the mark could never admit is a broken schema, not a bad call."""
    def annotate(name: str):
        return Annotated[
            str,
            Choices(values=(name,)),
            FileHint(extensions=(".png",), max_size=1_000_000),
        ]

    with pytest.raises(ValueError, match="not an accepted file type: 'default.gif'"):
        struct_of(make_dataclass("Wrong", [("image", annotate("default.gif"))]))

    schema = struct_of(make_dataclass("Right", [("image", annotate("default.png"))]))
    assert schema.resolve({"image": "default.png"}) == {"image": "default.png"}


# ----------------------------------------------------------------- defaults


def test_valid_default_is_certified_and_served():
    def process(image: Annotated[str, FileHint(extensions=(".png",))] = "default.png"):
        return image

    kwargs = signature_of(process).build({})
    assert kwargs == {"image": "default.png"}
    assert type(kwargs["image"]) is str


def test_a_default_naming_no_existing_file_is_still_certified():
    """Certification reads the schema and the text; there is no disk to disagree."""
    def process(image: Annotated[str, FileHint(min_size=4096)] = "not/on/disk.png"):
        return image

    assert signature_of(process).build({}) == {"image": "not/on/disk.png"}


def test_wrong_extension_default_fails_certification():
    def process(image: Annotated[str, FileHint(extensions=(".png",))] = "default.gif"):
        return image

    with pytest.raises(SchemaValueError) as error:
        signature_of(process)
    assert error.value.path == ("image", "default")
    assert error.value.leaf == (
        "not an accepted file type: 'default.gif', expected one of ('.png',)")


# --------------------------------------------------- lists and dataclasses


FilePath = Annotated[str, FileHint(extensions=(".pdf",), max_size=5 * 1024 * 1024)]


def test_list_of_files_needs_no_special_handling():
    model = make_dataclass("Batch", [("files", list[FilePath])])
    paths = [f"doc{i}.pdf" for i in range(3)]

    assert struct_of(model).resolve({"files": paths}) == {"files": paths}
    assert all(type(p) is str for p in struct_of(model).build({"files": paths}).files)


def test_dataclass_field_carries_the_contract():
    @dataclass
    class Request:
        image: Annotated[str, FileHint(extensions=(".png",))]

    built = struct_of(Request).build({"image": "image.png"})
    assert built == Request(image="image.png")
    assert type(built.image) is str


def test_error_keeps_the_field_path():
    @dataclass
    class Request:
        document: Annotated[str, FileHint(extensions=(".pdf",))]

    with pytest.raises(SchemaValueError) as error:
        struct_of(Request).resolve({"document": "notes.txt"})
    assert error.value.path == ("document",)
    assert error.value.leaf == (
        "not an accepted file type: 'notes.txt', expected one of ('.pdf',)")
    assert str(error.value) == (
        "document: not an accepted file type: 'notes.txt', "
        "expected one of ('.pdf',)")


def test_error_keeps_the_list_index():
    model = make_dataclass(
        "Batch", [("files", list[Annotated[str, FileHint(extensions=(".png",))]])])

    with pytest.raises(SchemaValueError) as error:
        struct_of(model).resolve({"files": ["a.png", "b.gif"]})
    assert error.value.path == ("files", 1)
    assert error.value.leaf == (
        "not an accepted file type: 'b.gif', expected one of ('.png',)")
    assert str(error.value) == (
        "files: [1]: not an accepted file type: 'b.gif', "
        "expected one of ('.png',)")


def test_nested_structures_keep_the_whole_path():
    @dataclass
    class Inner:
        images: list[Annotated[str, FileHint(extensions=(".png",))]]

    @dataclass
    class Outer:
        inner: Inner

    with pytest.raises(SchemaValueError) as error:
        struct_of(Outer).build({"inner": {"images": ["a.png", "b.gif"]}})
    assert error.value.path == ("inner", "images", 1)
    assert str(error.value) == (
        "inner: images: [1]: not an accepted file type: 'b.gif', "
        "expected one of ('.png',)")


# ---------------------------------------------------- the portable document


def test_the_document_node_writes_only_what_the_mark_declares():
    assert _str_node(Annotated[str, FileHint(extensions=(".png", ".jpg"))])["file_hint"] == {
        "extensions": [".png", ".jpg"]}
    assert _str_node(Annotated[str, FileHint(min_size=1)])["file_hint"] == {"min_size": 1}
    assert _str_node(Annotated[str, FileHint(max_size=9)])["file_hint"] == {"max_size": 9}


def test_a_mark_that_narrows_nothing_is_written_as_an_empty_object():
    # The empty object is the mark itself: this string names a file, and nothing
    # further is claimed about it.
    assert _str_node(Annotated[str, FileHint()])["file_hint"] == {}


def test_an_absent_mark_omits_the_key_entirely():
    assert "file_hint" not in _str_node(str)


# ---------------------------------------------------------- other constraints


def test_combines_with_pattern_min_max_and_choices():
    shape = Str(min=Min(1), max=Max(500), pattern=Pattern(r"[a-z]+\.png"),
                choices=Choices(values=("default.png",)),
                file_hint=FileHint(extensions=(".png",), min_size=1, max_size=1024))
    shape._check("default.png")

    # Length, pattern and choices keep applying to the text, exactly as the file
    # hint's extension does: every one of them is answered by the value alone.
    with pytest.raises(SchemaValueError, match="does not match pattern"):
        shape._check("Default.png")
    with pytest.raises(SchemaValueError, match="not a choice"):
        shape._check("other.png")


def test_length_bound_applies_to_the_text():
    shape = Str(max=Max(5), file_hint=FileHint(max_size=100_000))
    with pytest.raises(SchemaValueError, match="too long: 11 chars, maximum 5"):
        shape._check("default.png")


def test_hand_built_str_carries_the_mark():
    mark = FileHint(extensions=(".pdf",), min_size=1, max_size=10 * 1024 * 1024)
    shape = Str(file_hint=mark)

    assert shape.file_hint == mark
    assert shape == Str(file_hint=FileHint(
        extensions=(".pdf",), min_size=1, max_size=10 * 1024 * 1024))
    shape._check("doc.pdf")


def test_a_path_shaped_value_of_the_wrong_type_is_a_type_error():
    # `pathlib.Path` is not the type the field declares, and the mark does not
    # widen it: the value is a `str` or it is an error.
    with pytest.raises(TypeError) as error:
        Str(file_hint=FileHint(extensions=(".png",)))._check(Path("image.png"))
    assert "expected str, got" in str(error.value)


def test_optional_path_field_still_accepts_none():
    model = make_dataclass(
        "Optional",
        [("image", Annotated[str, FileHint(extensions=(".png",))] | None,
          field(default=None))])
    schema = struct_of(model)

    assert schema.resolve({"image": None}) == {"image": None}
    assert schema.resolve({"image": "image.png"}) == {"image": "image.png"}
    with pytest.raises((TypeError, ValueError)):
        schema.resolve({"image": "notes.txt"})

"""The `IsPathFile` file contract: extension, existence, regular file, size.

From 0.0.7 the mark guarantees that the string points at a real file at the
moment of validation. `pathlib.Path` is the inspection instrument only: every
value that passes stays the exact `str` it arrived as.
"""

from dataclasses import dataclass, field, make_dataclass
from pathlib import Path
from typing import Annotated

import pytest

from pytypehint import (
    Choices, IsPathFile, Max, Min, Pattern, SchemaValueError, signature_of,
    struct_of,
)
from pytypehint.shapes import Str


def _file(path: Path, size: int = 1) -> str:
    path.write_bytes(b"x" * size)
    return str(path)


def _symlink(link: Path, target: Path) -> str:
    """A symlink, or a clean skip where the platform or permissions refuse one."""
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symlinks unavailable on this platform: {error}")
    return str(link)


# ------------------------------------------------------- the file itself (1-6)


def test_existing_file_is_accepted(tmp_path):
    Str(is_path_file=IsPathFile())._check(_file(tmp_path / "report.pdf"))


def test_built_value_is_still_exactly_str(tmp_path):
    ImagePath = Annotated[str, IsPathFile(extensions=(".png",))]

    def process(image: ImagePath):
        return image

    target = _file(tmp_path / "image.png")
    kwargs = signature_of(process).build({"image": target})

    assert kwargs["image"] == target
    assert type(kwargs["image"]) is str


def test_accepted_extension_passes(tmp_path):
    shape = Str(is_path_file=IsPathFile(extensions=(".png", ".jpg")))
    shape._check(_file(tmp_path / "a.png"))
    shape._check(_file(tmp_path / "b.JPG"))


def test_rejected_extension_reports_the_accepted_set(tmp_path):
    shape = Str(is_path_file=IsPathFile(extensions=(".png", ".jpg")))
    target = _file(tmp_path / "image.gif")

    with pytest.raises(SchemaValueError) as error:
        shape._check(target)
    assert error.value.leaf == (
        f"not an accepted file type: {target!r}, "
        f"expected one of ('.png', '.jpg')")


def test_missing_path_reports_that_it_does_not_exist():
    with pytest.raises(SchemaValueError) as error:
        Str(is_path_file=IsPathFile(extensions=(".png",)))._check("missing.png")
    assert error.value.leaf == "file does not exist: 'missing.png'"


def test_directory_is_not_a_file(tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()

    with pytest.raises(SchemaValueError) as error:
        Str(is_path_file=IsPathFile())._check(str(folder))
    assert error.value.leaf == f"not a file: {str(folder)!r}"


def test_extension_is_checked_before_the_filesystem(tmp_path, monkeypatch):
    """The cheap constraint runs first: a wrong suffix never reaches `stat`."""
    target = _file(tmp_path / "image.gif")
    real_stat = Path.stat

    def refuse(self, *args, **kwargs):
        if self.name == "image.gif":
            raise AssertionError("stat reached despite a rejected extension")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", refuse)
    with pytest.raises(SchemaValueError, match="not an accepted file type"):
        Str(is_path_file=IsPathFile(extensions=(".png",)))._check(target)


# --------------------------------------------------------------- sizes (7-14)


def test_empty_file_passes_without_a_minimum(tmp_path):
    Str(is_path_file=IsPathFile())._check(_file(tmp_path / "empty.txt", 0))


def test_empty_file_fails_a_minimum_of_one(tmp_path):
    with pytest.raises(SchemaValueError) as error:
        Str(is_path_file=IsPathFile(min_size=1))._check(_file(tmp_path / "empty.txt", 0))
    assert error.value.leaf == "file too small: 0 bytes, minimum 1"


def test_size_equal_to_min_size_is_valid(tmp_path):
    Str(is_path_file=IsPathFile(min_size=100))._check(_file(tmp_path / "exact.bin", 100))


def test_size_equal_to_max_size_is_valid(tmp_path):
    Str(is_path_file=IsPathFile(max_size=100))._check(_file(tmp_path / "exact.bin", 100))


def test_size_below_min_size_is_rejected(tmp_path):
    with pytest.raises(SchemaValueError) as error:
        Str(is_path_file=IsPathFile(min_size=1024))._check(_file(tmp_path / "small.bin", 120))
    assert error.value.leaf == "file too small: 120 bytes, minimum 1024"


def test_size_above_max_size_is_rejected(tmp_path):
    with pytest.raises(SchemaValueError) as error:
        Str(is_path_file=IsPathFile(max_size=50))._check(_file(tmp_path / "big.bin", 51))
    assert error.value.leaf == "file too large: 51 bytes, maximum 50"


def test_min_size_zero_admits_every_size(tmp_path):
    shape = Str(is_path_file=IsPathFile(min_size=0))
    shape._check(_file(tmp_path / "empty.bin", 0))
    shape._check(_file(tmp_path / "one.bin", 1))


def test_max_size_zero_admits_only_an_empty_file(tmp_path):
    shape = Str(is_path_file=IsPathFile(max_size=0))
    shape._check(_file(tmp_path / "empty.bin", 0))

    with pytest.raises(SchemaValueError, match="file too large: 1 bytes, maximum 0"):
        shape._check(_file(tmp_path / "one.bin", 1))


def test_both_bounds_frame_the_accepted_range(tmp_path):
    shape = Str(is_path_file=IsPathFile(min_size=2, max_size=4))
    for size in (2, 3, 4):
        shape._check(_file(tmp_path / f"f{size}.bin", size))
    for size, message in ((1, "file too small"), (5, "file too large")):
        with pytest.raises(SchemaValueError, match=message):
            shape._check(_file(tmp_path / f"f{size}.bin", size))


# --------------------------------------------- atom argument validation (15-20)


@pytest.mark.parametrize("kwargs, message", [
    ({"min_size": True}, "IsPathFile.min_size must be int or None, got bool"),
    ({"max_size": False}, "IsPathFile.max_size must be int or None, got bool"),
    ({"min_size": 1.5}, "IsPathFile.min_size must be int or None, got float"),
    ({"max_size": 1.5}, "IsPathFile.max_size must be int or None, got float"),
    ({"min_size": "10"}, "IsPathFile.min_size must be int or None, got str"),
    ({"max_size": "10"}, "IsPathFile.max_size must be int or None, got str"),
])
def test_size_must_be_int_or_none(kwargs, message):
    with pytest.raises(TypeError) as error:
        IsPathFile(**kwargs)
    assert str(error.value) == message


@pytest.mark.parametrize("kwargs, message", [
    ({"min_size": -1}, "IsPathFile.min_size must be >= 0, got -1"),
    ({"max_size": -1}, "IsPathFile.max_size must be >= 0, got -1"),
])
def test_size_must_not_be_negative(kwargs, message):
    with pytest.raises(ValueError) as error:
        IsPathFile(**kwargs)
    assert str(error.value) == message


def test_min_size_may_not_exceed_max_size():
    with pytest.raises(ValueError) as error:
        IsPathFile(min_size=100, max_size=50)
    assert str(error.value) == "IsPathFile: min_size 100 exceeds max_size 50"


@pytest.mark.parametrize("size", [None, 0, 1, 1024, 5 * 1024 * 1024])
def test_valid_sizes_are_accepted_on_both_bounds(size):
    IsPathFile(min_size=size)
    IsPathFile(max_size=size)


def test_equal_bounds_are_valid():
    IsPathFile(min_size=10, max_size=10)


# --------------------------------------------------------------- choices (21-24)


def test_choices_accept_a_file_meeting_the_whole_contract(tmp_path):
    target = _file(tmp_path / "default.png")
    shape = Str(choices=Choices(values=(target,)),
                is_path_file=IsPathFile(extensions=(".png",), max_size=1_000_000))
    shape._check(target)


def test_choices_reject_a_file_that_does_not_exist():
    with pytest.raises(ValueError) as error:
        Str(choices=Choices(values=("missing.png",)),
            is_path_file=IsPathFile(extensions=(".png",)))
    assert str(error.value) == "Str.choices: file does not exist: 'missing.png'"


def test_choices_reject_a_wrong_extension(tmp_path):
    target = _file(tmp_path / "notes.txt")
    with pytest.raises(ValueError, match=r"Str\.choices: not an accepted file type"):
        Str(choices=Choices(values=(target,)),
            is_path_file=IsPathFile(extensions=(".png",)))


def test_choices_reject_a_file_outside_the_size_bounds(tmp_path):
    target = _file(tmp_path / "big.png", 200)
    with pytest.raises(ValueError) as error:
        Str(choices=Choices(values=(target,)),
            is_path_file=IsPathFile(extensions=(".png",), max_size=100))
    assert str(error.value) == "Str.choices: file too large: 200 bytes, maximum 100"


def test_choices_reject_a_directory(tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    with pytest.raises(ValueError, match=r"Str\.choices: not a file"):
        Str(choices=Choices(values=(str(folder),)), is_path_file=IsPathFile())


def test_choices_are_certified_through_compilation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    hint = Annotated[
        str,
        Choices(values=("default.png",)),
        IsPathFile(extensions=(".png",), max_size=1_000_000),
    ]

    with pytest.raises(ValueError, match="file does not exist: 'default.png'"):
        struct_of(make_dataclass("Missing", [("image", hint)]))

    _file(tmp_path / "default.png")
    schema = struct_of(make_dataclass("Present", [("image", hint)]))
    assert schema.resolve({"image": "default.png"}) == {"image": "default.png"}


# --------------------------------------------------------------- defaults (25-27)


def test_valid_default_is_certified_and_served(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _file(tmp_path / "default.png")

    def process(image: Annotated[str, IsPathFile()] = "default.png"):
        return image

    kwargs = signature_of(process).build({})
    assert kwargs == {"image": "default.png"}
    assert type(kwargs["image"]) is str


def test_missing_default_fails_certification(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def process(image: Annotated[str, IsPathFile()] = "default.png"):
        return image

    with pytest.raises(SchemaValueError) as error:
        signature_of(process)
    assert error.value.path == ("image", "default")
    assert error.value.leaf == "file does not exist: 'default.png'"


def test_oversized_default_fails_certification(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _file(tmp_path / "default.png", 200)

    def process(image: Annotated[str, IsPathFile(max_size=100)] = "default.png"):
        return image

    with pytest.raises(SchemaValueError) as error:
        signature_of(process)
    assert error.value.path == ("image", "default")
    assert error.value.leaf == "file too large: 200 bytes, maximum 100"


def test_directory_default_fails_certification(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "folder").mkdir()

    def process(image: Annotated[str, IsPathFile()] = "folder"):
        return image

    with pytest.raises(SchemaValueError, match=r"image: default: not a file: 'folder'"):
        signature_of(process)


def test_wrong_extension_default_fails_certification(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _file(tmp_path / "default.gif")

    def process(image: Annotated[str, IsPathFile(extensions=(".png",))] = "default.gif"):
        return image

    with pytest.raises(SchemaValueError, match="not an accepted file type"):
        signature_of(process)


# ------------------------------------------------ lists and dataclasses (28-31)


FilePath = Annotated[str, IsPathFile(extensions=(".pdf",), max_size=5 * 1024 * 1024)]


def test_list_of_files_needs_no_special_handling(tmp_path):
    model = make_dataclass("Batch", [("files", list[FilePath])])
    paths = [_file(tmp_path / f"doc{i}.pdf") for i in range(3)]

    assert struct_of(model).resolve({"files": paths}) == {"files": paths}
    assert all(type(p) is str for p in struct_of(model).build({"files": paths}).files)


def test_dataclass_field_carries_the_contract(tmp_path):
    @dataclass
    class Request:
        image: Annotated[str, IsPathFile(extensions=(".png",))]

    target = _file(tmp_path / "image.png")
    built = struct_of(Request).build({"image": target})
    assert built == Request(image=target)
    assert type(built.image) is str


def test_error_keeps_the_field_path(tmp_path):
    @dataclass
    class Request:
        document: Annotated[str, IsPathFile(extensions=(".pdf",))]

    with pytest.raises(SchemaValueError) as error:
        struct_of(Request).resolve({"document": "missing.pdf"})
    assert error.value.path == ("document",)
    assert error.value.leaf == "file does not exist: 'missing.pdf'"
    assert str(error.value) == "document: file does not exist: 'missing.pdf'"


def test_error_keeps_the_list_index(tmp_path):
    model = make_dataclass(
        "Batch", [("files", list[Annotated[str, IsPathFile(max_size=5_242_880)]])])
    small = _file(tmp_path / "a.bin")
    big = _file(tmp_path / "b.bin", 5_242_881)

    with pytest.raises(SchemaValueError) as error:
        struct_of(model).resolve({"files": [small, big]})
    assert error.value.path == ("files", 1)
    assert error.value.leaf == "file too large: 5242881 bytes, maximum 5242880"
    assert str(error.value) == "files: [1]: file too large: 5242881 bytes, maximum 5242880"


def test_nested_structures_keep_the_whole_path(tmp_path):
    @dataclass
    class Inner:
        images: list[Annotated[str, IsPathFile(extensions=(".png",))]]

    @dataclass
    class Outer:
        inner: Inner

    good = _file(tmp_path / "a.png")
    with pytest.raises(SchemaValueError) as error:
        struct_of(Outer).build({"inner": {"images": [good, "missing.png"]}})
    assert error.value.path == ("inner", "images", 1)
    assert str(error.value) == "inner: images: [1]: file does not exist: 'missing.png'"


# ----------------------------------------------------------- symlinks (32-33)


def test_live_symlink_to_a_regular_file_is_accepted(tmp_path):
    target = tmp_path / "real.png"
    target.write_bytes(b"x")
    link = _symlink(tmp_path / "link.png", target)

    Str(is_path_file=IsPathFile(extensions=(".png",), min_size=1))._check(link)


def test_symlink_reports_the_size_of_its_target(tmp_path):
    target = tmp_path / "real.bin"
    target.write_bytes(b"x" * 200)
    link = _symlink(tmp_path / "link.bin", target)

    with pytest.raises(SchemaValueError, match="file too large: 200 bytes, maximum 100"):
        Str(is_path_file=IsPathFile(max_size=100))._check(link)


def test_broken_symlink_fails_as_a_missing_file(tmp_path):
    link = _symlink(tmp_path / "link.png", tmp_path / "gone.png")

    with pytest.raises(SchemaValueError) as error:
        Str(is_path_file=IsPathFile(extensions=(".png",)))._check(link)
    assert error.value.leaf == f"file does not exist: {link!r}"


def test_symlink_to_a_directory_is_not_a_file(tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    link = _symlink(tmp_path / "link", folder)

    with pytest.raises(SchemaValueError, match="not a file"):
        Str(is_path_file=IsPathFile())._check(link)


# ------------------------------------------------------- inspection errors (34)


def test_inspection_oserror_is_reported_with_its_cause(tmp_path, monkeypatch):
    target = _file(tmp_path / "locked.bin")
    real_stat = Path.stat

    def refuse(self, *args, **kwargs):
        if self.name == "locked.bin":
            raise PermissionError(13, "Permission denied")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", refuse)
    with pytest.raises(SchemaValueError) as error:
        Str(is_path_file=IsPathFile())._check(target)

    assert error.value.leaf.startswith(f"cannot inspect file {target!r}: PermissionError:")
    assert type(error.value.__cause__) is PermissionError


def test_unparsable_path_is_reported_as_a_failed_inspection():
    # An embedded null byte raises ValueError rather than OSError; it is still a
    # failed inspection and stays inside the structured error contract.
    with pytest.raises(SchemaValueError) as error:
        Str(is_path_file=IsPathFile())._check("a\0b")
    assert error.value.leaf.startswith("cannot inspect file 'a\\x00b': ValueError:")


# ------------------------------------------------- other constraints (35-36)


def test_combines_with_pattern_min_max_and_choices(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _file(tmp_path / "default.png", 10)

    shape = Str(min=Min(1), max=Max(500), pattern=Pattern(r"[a-z]+\.png"),
                choices=Choices(values=("default.png",)),
                is_path_file=IsPathFile(extensions=(".png",), min_size=1, max_size=1024))
    shape._check("default.png")

    # Length, pattern and choices keep applying to the path text; IsPathFile
    # applies to the file it names.
    with pytest.raises(SchemaValueError, match="does not match pattern"):
        shape._check("Default.png")
    _file(tmp_path / "other.png", 10)
    with pytest.raises(SchemaValueError, match="not a choice"):
        shape._check("other.png")


def test_length_bound_applies_to_the_text_not_the_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _file(tmp_path / "default.png", 10_000)

    shape = Str(max=Max(5), is_path_file=IsPathFile(max_size=100_000))
    with pytest.raises(SchemaValueError, match="too long: 11 chars, maximum 5"):
        shape._check("default.png")


def test_hand_built_str_carries_the_mark(tmp_path):
    mark = IsPathFile(extensions=(".pdf",), min_size=1, max_size=10 * 1024 * 1024)
    shape = Str(is_path_file=mark)

    assert shape.is_path_file == mark
    assert shape == Str(is_path_file=IsPathFile(
        extensions=(".pdf",), min_size=1, max_size=10 * 1024 * 1024))
    shape._check(_file(tmp_path / "doc.pdf"))


def test_a_path_shaped_value_of_the_wrong_type_is_a_type_error(tmp_path):
    target = tmp_path / "image.png"
    target.write_bytes(b"x")

    with pytest.raises(TypeError) as error:
        Str(is_path_file=IsPathFile(extensions=(".png",)))._check(target)
    assert "expected str, got" in str(error.value)


def test_relative_path_follows_the_working_directory(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    _file(tmp_path / "data" / "image.png")

    shape = Str(is_path_file=IsPathFile(extensions=(".png",)))
    monkeypatch.chdir(tmp_path)
    # The value is validated relative to the working directory and stays exactly
    # as written: no normalization, no absolute rewrite.
    value = "data/image.png"
    shape._check(value)
    assert value == "data/image.png"

    monkeypatch.chdir(tmp_path / "data")
    with pytest.raises(SchemaValueError, match="file does not exist"):
        shape._check(value)


def test_optional_path_field_still_accepts_none(tmp_path):
    model = make_dataclass(
        "Optional",
        [("image", Annotated[str, IsPathFile(extensions=(".png",))] | None,
          field(default=None))])
    schema = struct_of(model)

    assert schema.resolve({"image": None}) == {"image": None}
    target = _file(tmp_path / "image.png")
    assert schema.resolve({"image": target}) == {"image": target}
    with pytest.raises((TypeError, ValueError)):
        schema.resolve({"image": "missing.png"})

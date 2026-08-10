"""Executable contract for README.md and docs/*.md.

The documentation deliberately repeats its central promises.  This module
groups equivalent claims into one test and names the source documents in each
section so that prose and behaviour cannot silently drift apart.
"""

import json
from copy import deepcopy
from dataclasses import InitVar, dataclass, field, make_dataclass
from itertools import combinations
from datetime import date, datetime, time, timezone
from enum import Enum, Flag
from typing import Annotated, Literal

import pytest

import pytypehint
from pytypehint import (
    Choices, Description, Extra, Field, FileHint, Int, Label, Max, Min,
    MultipleOf, OptionalToggle, Pattern, SchemaTypeError, SchemaValueError,
    Signature, Slider, Struct, signature_of, struct_of,
)
from pytypehint.shapes import (
    Bool, Date, EnumShape, Float, List, NoneShape, Str, Time,
)
from pytypehint.structure import _portable_options, _wrapped_options


# README example; README "Guarantees"; docs/build.md.
@dataclass(frozen=True)
class _Page:
    number: Annotated[int, Min(1)] = 1
    size: Annotated[int, Min(1), Max(100), Label("Page size")] = 20


@dataclass
class _Search:
    query: str
    page: _Page = _Page()
    tags: list[str] = field(default_factory=list)


def test_readme_example_is_executable_and_reports_the_documented_error():
    schema = struct_of(_Search)
    assert schema.build({"query": "python", "page": {"size": 50}}) == _Search(
        query="python", page=_Page(number=1, size=50), tags=[])

    with pytest.raises(ValueError) as error:
        schema.build({"query": "python", "page": {"size": 500}})
    assert str(error.value) == "page: size: too large: 500, maximum 100"


# README "Public API".
def test_every_documented_public_name_is_exported_from_the_package():
    documented = {
        "struct_of", "signature_of", "Struct", "Field", "Signature",
        "SchemaTypeError", "SchemaValueError", "Shape", "Int", "Float",
        "Str", "Bool", "Date", "Time", "List", "NoneShape", "EnumShape",
        "Min", "Max", "Choices", "MultipleOf", "Pattern", "FileHint",
        "Label", "Description", "Placeholder", "Step", "Slider",
        "IsPassword", "Rows", "Extra", "OptionalToggle", "MISSING",
    }
    assert documented <= set(pytypehint.__all__)
    assert all(hasattr(pytypehint, name) for name in documented)


# README "Vocabulary"; docs/vocabulary.md; docs/philosophy.md "Hints are exact".
@pytest.mark.parametrize("shape, good, bad", [
    (Int(), 1, True),
    (Float(), 1.0, 1),
    (Str(), "1", 1),
    (Bool(), True, 1),
    (Date(), date(2024, 1, 1), datetime(2024, 1, 1)),
    (Time(), time(12, 0), "12:00"),
    (NoneShape(), None, 0),
])
def test_documented_scalar_vocabulary_uses_exact_types(shape, good, bad):
    shape._check(good)
    with pytest.raises(TypeError):
        shape._check(bad)


def test_time_is_naive_and_floats_are_finite():
    with pytest.raises(ValueError, match=r"must be naive"):
        Time()._check(time(12, tzinfo=timezone.utc))
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match=r"not finite"):
            Float()._check(value)


class _Role(Enum):
    ADMIN = "admin"


class _OtherRole(Enum):
    ADMIN = "admin"


def test_enum_input_must_be_a_member_of_the_exact_enum():
    shape = EnumShape(cls=_Role)
    shape._check(_Role.ADMIN)
    for wrong in ("admin", _OtherRole.ADMIN):
        with pytest.raises(TypeError):
            shape._check(wrong)


# docs/vocabulary.md list, nesting, union, None-item and Literal claims.
@dataclass
class _Collections:
    matrix: list[list[int]]
    holes: list[int | None]
    mode: Literal["fast", "safe"]


def test_nested_lists_none_items_and_literals_match_the_vocabulary_table():
    schema = struct_of(_Collections)
    assert schema.resolve({
        "matrix": [[1], [2, 3]], "holes": [1, None, 2], "mode": "fast",
    }) == {"matrix": [[1], [2, 3]], "holes": [1, None, 2], "mode": "fast"}

    with pytest.raises(TypeError, match=r"matrix: \[0\]: \[1\]: expected int"):
        schema.resolve({"matrix": [[1, "2"]], "holes": [], "mode": "fast"})
    with pytest.raises(ValueError, match=r"mode: not a choice"):
        schema.resolve({"matrix": [], "holes": [], "mode": "FAST"})


# docs/atoms.md accepted semantics and compile-time cross-checks.
def test_limit_atoms_validate_and_notation_atoms_only_describe():
    @dataclass
    class Model:
        value: Annotated[
            int, Min(0), Max(10), MultipleOf(2), Label("Value"),
            Description("Even"), Extra("widget.kind", "dial"),
        ]

    compiled = struct_of(Model)
    fld = compiled.fields[0]
    assert fld.label == Label("Value")
    assert fld.description == Description("Even")
    assert fld.shape[0].extras == {"widget.kind": "dial"}
    assert compiled.resolve({"value": 4}) == {"value": 4}
    with pytest.raises(ValueError, match=r"not a multiple"):
        compiled.resolve({"value": 3})


@pytest.mark.parametrize("hint, message", [
    (Annotated[int, Min(2), Max(1)], "empty range"),
    (Annotated[int, Min(0), Choices(values=(-1,))], "below minimum"),
    (Annotated[int, Slider()], "slider requires min and max"),
    (Annotated[int, OptionalToggle(True)], r"requires an optional field"),
])
def test_documented_atom_contradictions_fail_at_compilation(hint, message):
    model = make_dataclass("DocumentedContradiction", [("value", hint)])
    with pytest.raises((TypeError, ValueError), match=message):
        struct_of(model)


# docs/atoms.md, docs/restrictions.md, docs/philosophy.md and README
# "Guarantees" on FileHint: the core states the file's contract and checks the
# one part of it the value itself answers.
def test_file_hint_validates_the_extension_and_keeps_the_value_a_str():
    FilePath = Annotated[str, FileHint(extensions=(".pdf",), max_size=10 * 1024 * 1024)]
    model = make_dataclass("Upload", [("document", FilePath)])
    schema = struct_of(model)

    # No file is written anywhere in this test, and that is the point: the
    # extension is spelled in the value, so the verdict comes from the text.
    built = schema.build({"document": "report.pdf"})
    assert built.document == "report.pdf"
    assert type(built.document) is str

    with pytest.raises(SchemaValueError) as error:
        schema.resolve({"document": "report.txt"})
    assert str(error.value) == (
        "document: not an accepted file type: 'report.txt', "
        "expected one of ('.pdf',)")


def test_file_hint_states_the_sizes_without_ever_checking_them(tmp_path):
    """The sizes are the wrapper's to apply, so they travel and are not tested.

    A file that exists and breaks both bounds is accepted here, because reading
    it would be the core asking the world a question whose answer is only true
    at the boundary that has the file in hand.
    """
    marked = Annotated[str, FileHint(min_size=1024, max_size=2048)]
    schema = struct_of(make_dataclass("Upload", [("document", marked)]))

    target = tmp_path / "tiny.bin"
    target.write_bytes(b"x")
    assert schema.build({"document": str(target)}).document == str(target)

    target.unlink()
    assert schema.build({"document": str(target)}).document == str(target)

    node = schema.to_dict()["defs"]["structs"]["Upload"]["fields"][0]["shape"][0]
    assert node["file_hint"] == {"min_size": 1024, "max_size": 2048}


def test_file_hint_certifies_defaults_and_choices_by_extension(tmp_path, monkeypatch):
    """docs/defaults.md and docs/atoms.md: certified under the part that is text."""
    monkeypatch.chdir(tmp_path)

    def process(image: Annotated[str, FileHint(extensions=(".png",))] = "default.gif"):
        return image

    with pytest.raises(SchemaValueError) as error:
        signature_of(process)
    assert str(error.value) == (
        "image: default: not an accepted file type: 'default.gif', "
        "expected one of ('.png',)")

    with pytest.raises(ValueError, match=r"Str\.choices: not an accepted file type"):
        struct_of(make_dataclass("Offered", [(
            "image",
            Annotated[str, Choices(values=("default.gif",)), FileHint(extensions=(".png",))])]))

    # The named file has never existed, in this directory or any other, and the
    # signature compiles and serves its default all the same.
    def offered(image: Annotated[str, FileHint(extensions=(".png",))] = "default.png"):
        return image

    assert signature_of(offered).build({}) == {"image": "default.png"}


def test_pattern_uses_fullmatch_and_custom_message():
    shape = Str(pattern=Pattern(r"\d+", message="digits only"))
    shape._check("123")
    with pytest.raises(ValueError, match=r"^digits only$"):
        shape._check("123x")


def test_atom_layering_uses_outer_or_rightmost_value():
    Percent = Annotated[int, Min(0), Max(100)]
    Narrow = Annotated[Percent, Max(50)]
    Optional = Annotated[int | None, OptionalToggle(True)]
    Closed = Annotated[Optional, OptionalToggle(False)]

    model = make_dataclass("Layered", [("n", Narrow), ("optional", Closed)])
    n, optional = struct_of(model).fields
    assert n.shape[0].max == Max(50)
    assert optional.optional_toggle == OptionalToggle(False)


def test_extra_layering_and_read_only_snapshot_match_atoms_documentation():
    Themed = Annotated[
        int, Extra("ledform.color", "red"), Extra("ledform.rows", "2")]
    Blue = Annotated[Themed, Extra("ledform.color", "blue")]
    model = make_dataclass("ThemedModel", [("value", Blue)])
    shape = struct_of(model).fields[0].shape[0]

    assert shape.extras == {"ledform.color": "blue", "ledform.rows": "2"}
    snapshot = shape.extras
    snapshot.clear()
    assert shape.extras == {"ledform.color": "blue", "ledform.rows": "2"}


# docs/build.md and docs/resolve.md.
@dataclass
class _File:
    path: str


@dataclass
class _Url:
    value: str


@dataclass
class _Source:
    value: _File | _Url


def test_resolve_preserves_and_build_consumes_dataclass_union_discriminator():
    data = {"value": {"$type": "_Url", "value": "https://example.test"}}
    schema = struct_of(_Source)
    assert schema.resolve(data) == data
    assert schema.build(data) == _Source(value=_Url("https://example.test"))


@pytest.mark.parametrize("payload, message", [
    ({"value": {"value": "x"}}, r"ambiguous dict"),
    ({"value": {"$type": "Other", "value": "x"}}, r"\$type: not a choice"),
    ({"value": {"$type": 1, "value": "x"}}, r"\$type: expected str"),
])
def test_documented_discriminator_failures(payload, message):
    with pytest.raises((TypeError, ValueError), match=message):
        struct_of(_Source).build(payload)


# README "Vocabulary"; docs/vocabulary.md; docs/build.md "$type and $value".
@dataclass
class _Terms:
    mixed: list[str | int]
    either: list[str] | list[int]


def test_a_union_item_and_a_union_of_lists_are_documented_as_different_things():
    schema = struct_of(_Terms)
    data = {"mixed": ["a", 1, "b", 2],
            "either": {"$type": "list[str]", "$value": ["a", "b"]}}

    assert schema.resolve(data) == data
    assert schema.build(data) == _Terms(mixed=["a", 1, "b", 2], either=["a", "b"])


@pytest.mark.parametrize("value, message", [
    (["a"], r"ambiguous list: field accepts list\[str\] \| list\[int\]"),
    ({"$type": "list[float]", "$value": []}, r"\$type: not a choice: 'list\[float\]'"),
    ({"$type": 1, "$value": []}, r"\$type: expected str, got int"),
    ({"$type": "list[str]"}, r"missing key\(s\): \$value"),
    ({"$type": "list[str]", "$value": [], "note": 1}, r"unexpected key\(s\): note"),
    ({"$type": "list[str]", "$value": ["a", 1]}, r"\$value: \[1\]: expected str, got int"),
])
def test_documented_wrapper_failures(value, message):
    with pytest.raises((TypeError, ValueError), match=message):
        struct_of(_Terms).build({"mixed": [], "either": value})


# docs/restrictions.md "Option identity".
@pytest.mark.parametrize("shape, option_id", [
    (Int(), "int"),
    (Str(), "str"),
    (NoneShape(), "None"),
    (EnumShape(cls=_Role), "_Role"),
    (List(item=(Str(),)), "list[str]"),
    (List(item=(Int(), NoneShape())), "list[int | None]"),
    (List(item=(List(item=(Str(),)),)), "list[list[str]]"),
])
def test_option_identity_matches_the_documented_table(shape, option_id):
    assert shape.option_id() == option_id


def test_options_sharing_a_runtime_type_and_an_identity_are_still_rejected():
    """docs/restrictions.md: 'they may not also share an identity'."""
    model = make_dataclass("Indistinguishable", [
        ("x", list[Annotated[int, Min(0)]] | list[Annotated[int, Max(9)]])])

    with pytest.raises(ValueError, match=r"duplicate option types in shape"):
        struct_of(model)


def test_signature_build_constructs_kwargs_without_calling_the_function():
    calls = []

    def run(page: _Page = _Page()):
        calls.append(page)

    kwargs = signature_of(run).build({"page": {"size": 50}})
    assert kwargs == {"page": _Page(size=50)}
    assert calls == []


def test_resolve_keeps_nested_dicts_while_build_constructs_instances():
    resolved = struct_of(_Search).resolve({"query": "x", "page": {"size": 30}})
    built = struct_of(_Search).build({"query": "x", "page": {"size": 30}})
    # resolve validates the supplied nested dictionary as-is; build crosses the
    # construction boundary and serves the nested dataclass's missing default.
    assert resolved["page"] == {"size": 30}
    assert type(resolved["page"]) is dict
    assert built.page == _Page(number=1, size=30)


def test_input_dataclass_instances_are_rejected_by_resolve_and_build():
    schema = struct_of(_Search)
    data = {"query": "x", "page": _Page()}
    for operation in (schema.resolve, schema.build):
        with pytest.raises(TypeError, match=r"page: expected dict, got _Page instance"):
            operation(data)


# docs/defaults.md and docs/philosophy.md "Defaults are recipes".
def test_default_factory_is_certified_once_and_run_once_per_missing_serving():
    calls = []

    def recipe():
        calls.append(len(calls))
        return [1]

    model = make_dataclass(
        "RecipeModel", [("values", list[int], field(default_factory=recipe))])
    schema = struct_of(model)
    assert len(calls) == 1

    first = schema.resolve({})["values"]
    second = schema.build({}).values
    assert len(calls) == 3
    assert first == second == [1]
    assert first is not second

    assert schema.resolve({"values": [2]}) == {"values": [2]}
    assert len(calls) == 3


def test_impure_default_is_revalidated_with_a_default_path_segment():
    values = iter((1, 2))
    model = make_dataclass(
        "Impure", [("n", Annotated[int, Max(1)], field(default_factory=lambda: next(values)))])
    schema = struct_of(model)
    with pytest.raises(ValueError) as error:
        schema.resolve({})
    assert error.value.path == ("n", "default")
    assert error.value.leaf == "too large: 2, maximum 1"


# README guarantees; docs/philosophy.md identity and fail-fast claims.
def test_struct_field_and_signature_use_identity_equality():
    def fn(value: int):
        pass

    assert struct_of(_Search) != struct_of(_Search)
    assert Field(name="x", shape=(Int(),)) != Field(name="x", shape=(Int(),))
    assert signature_of(fn) != signature_of(fn)
    assert isinstance(struct_of(_Search), Struct)
    assert isinstance(signature_of(fn), Signature)


def test_schema_errors_preserve_path_leaf_and_builtin_error_subclass():
    @dataclass
    class Model:
        values: list[Annotated[int, Max(1)]]

    with pytest.raises(SchemaValueError) as value_error:
        struct_of(Model).resolve({"values": [0, 2]})
    assert value_error.value.path == ("values", 1)
    assert value_error.value.leaf == "too large: 2, maximum 1"
    assert isinstance(value_error.value, ValueError)

    with pytest.raises(SchemaTypeError) as type_error:
        struct_of(Model).resolve({"values": ["0"]})
    assert type_error.value.path == ("values", 0)
    assert type_error.value.leaf == "expected int, got str"
    assert isinstance(type_error.value, TypeError)


# docs/restrictions.md: closed vocabulary and structural restrictions.
@pytest.mark.parametrize("hint, message", [
    (complex, r"unsupported type: <class 'complex'>"),
    (list, r"list requires an item type: list\[X\]"),
    (None, r"None must be accompanied by another option"),
    (datetime, r"unsupported type: <class 'datetime.datetime'>"),
])
def test_documented_unsupported_field_hints_fail_with_useful_messages(hint, message):
    model = make_dataclass("Unsupported", [("x", hint)])
    with pytest.raises((TypeError, ValueError), match=message):
        struct_of(model)


def test_signature_restrictions_cover_variadics_positional_only_missing_hints_and_lambda():
    def variadic(*args: int):
        pass

    def positional(x: int, /):
        pass

    def missing(x):
        pass

    cases = [
        (variadic, r"args: variadic parameters"),
        (positional, r"x: positional-only parameters"),
        (missing, r"x: missing type hint"),
        (lambda x: x, r"lambdas have no usable name"),
    ]
    for fn, message in cases:
        with pytest.raises(TypeError, match=message):
            signature_of(fn)


def test_dataclass_initvar_and_init_false_are_rejected():
    @dataclass
    class WithInitVar:
        value: InitVar[int]

    @dataclass
    class WithInitFalse:
        value: int = field(init=False, default=1)

    with pytest.raises(TypeError, match=r"value: InitVar fields are not supported"):
        struct_of(WithInitVar)
    with pytest.raises(TypeError, match=r"value: init=False fields are not supported"):
        struct_of(WithInitFalse)


class _Flags(Flag):
    A = 1
    B = 2


class _EmptyEnum(Enum):
    pass


def test_flag_and_empty_enums_are_rejected_as_documented():
    with pytest.raises(TypeError, match=r"Flag enums are not supported"):
        EnumShape(cls=_Flags)
    with pytest.raises(ValueError, match=r"enum has no members"):
        EnumShape(cls=_EmptyEnum)


def test_extra_restrictions_match_the_documented_messages():
    with pytest.raises(ValueError, match=r"must be namespaced"):
        Extra("color", "red")
    with pytest.raises(ValueError, match=r"must not be empty"):
        Extra("", "red")
    with pytest.raises(TypeError, match=r"Extra\.key must be str"):
        Extra(1, "red")
    with pytest.raises(TypeError, match=r"Extra\.value must be str"):
        Extra("pkg.color", 1)


# README "The four operations"; docs/decode.md.
@dataclass
class _User:
    name: str
    birthday: date


def test_readme_decode_example_prepares_what_build_refuses_to_accept():
    schema = struct_of(_User)
    wire = {"name": "Ana", "birthday": "2000-05-17"}

    assert schema.decode(wire) == {"name": "Ana", "birthday": date(2000, 5, 17)}
    assert schema.build(schema.decode(wire)) == _User("Ana", date(2000, 5, 17))

    with pytest.raises(SchemaTypeError) as error:
        schema.build(wire)
    assert str(error.value) == "birthday: expected date, got str"


@dataclass
class _Example:
    count: int


# README "decode is not coercion"; docs/decode.md; docs/philosophy.md.
@pytest.mark.parametrize("hint, value", [
    (int, "10"), (int, "1"), (float, "1.0"), (float, "1.5"),
    (bool, "true"), (bool, "false"), (bool, 1), (int, True),
    (str, 1), (list[int], (1, 2)),
])
def test_decode_never_coerces_a_value_the_transport_represented_faithfully(hint, value):
    model = make_dataclass("NotCoerced", [("v", hint)])
    schema = struct_of(model)
    assert schema.decode({"v": value}) == {"v": value}
    with pytest.raises((TypeError, ValueError)):
        schema.build(schema.decode({"v": value}))


def test_a_str_field_keeps_text_that_merely_looks_like_a_date():
    """docs/decode.md: 'the shape decides the reading; the text never does'."""
    model = make_dataclass("Post", [("slug", str)])
    assert struct_of(model).decode({"slug": "2026-08-08"}) == {"slug": "2026-08-08"}


# docs/decode.md "Canonical spellings".
@pytest.mark.parametrize("text", [
    "20260808", "2026-W32-6", "2026-08-08T10:00", "2026/08/08", "2026-02-31", "hello",
])
def test_only_the_canonical_date_spelling_is_read_and_the_rest_stay_str(text):
    model = make_dataclass("Booking", [("day", date)])
    assert struct_of(model).decode({"day": text}) == {"day": text}


def test_the_canonical_date_and_time_spellings_are_read():
    model = make_dataclass("When", [("day", date), ("at", time)])
    schema = struct_of(model)
    assert schema.decode({"day": "2026-08-08", "at": "14:30"}) == {
        "day": date(2026, 8, 8), "at": time(14, 30)}
    assert schema.decode({"at": "14:30:00"}) == {"at": time(14, 30)}


def test_a_time_the_schema_refuses_is_still_read_so_the_shape_reports_its_own_rule():
    """docs/decode.md: the shape reports its rule instead of the value falling through."""
    model = make_dataclass("Slot", [("at", time)])
    schema = struct_of(model)
    for text, message in [
            ("10:00:00.5", "at: time precision is limited to whole seconds: 10:00:00.500000"),
            ("10:00:00+02:00", "at: must be naive (no tzinfo): 10:00:00+02:00")]:
        with pytest.raises(SchemaValueError) as error:
            schema.build(schema.decode({"at": text}))
        assert str(error.value) == message


class _Cross(Enum):
    RED = "BLUE"
    BLUE = "RED"


def test_enum_members_travel_by_name_and_arrive_as_the_member_itself():
    """docs/decode.md: 'The name, not the value.'"""
    model = make_dataclass("Painted", [("colour", _Cross)])
    schema = struct_of(model)
    assert schema.decode({"colour": "RED"})["colour"] is _Cross.RED
    assert schema.decode({"colour": "GREEN"}) == {"colour": "GREEN"}


# docs/decode.md "Unions".
@dataclass
class _Query:
    terms: list[str] | list[int]
    when: str | date


def test_a_wrapper_is_kept_where_build_needs_it_and_consumed_where_it_does_not():
    schema = struct_of(_Query)
    decoded = schema.decode({"terms": {"$type": "list[str]", "$value": ["a"]},
                             "when": {"$type": "date", "$value": "2026-08-08"}})
    # The two lists share a Python type, so validation still routes by the
    # discriminator; str and date do not, so the exact value is enough.
    assert decoded == {"terms": {"$type": "list[str]", "$value": ["a"]},
                       "when": date(2026, 8, 8)}
    assert schema.build(decoded) == _Query(terms=["a"], when=date(2026, 8, 8))


def test_a_wrapper_whose_payload_missed_its_option_is_left_for_validation_to_report():
    """docs/decode.md: consuming it would file the value under another option in silence."""
    schema = struct_of(_Query)
    wrapper = {"$type": "date", "$value": "nonsense"}
    terms = {"$type": "list[str]", "$value": []}
    decoded = schema.decode({"terms": terms, "when": wrapper})
    assert decoded["when"] == wrapper

    with pytest.raises(SchemaTypeError) as error:
        schema.build(decoded)
    assert str(error.value) == "when: expected str | date, got dict"


@pytest.mark.parametrize("value", [[], ["a"], [1], [1, "a"]])
def test_an_ambiguous_list_is_never_decoded_into_a_branch(value):
    """docs/decode.md: a colliding spelling decodes to nothing at all."""
    schema = struct_of(_Query)
    assert schema.decode({"terms": value})["terms"] == value
    with pytest.raises(SchemaTypeError, match=r"ambiguous list"):
        schema.build({"terms": value, "when": "x"})


def test_decode_fills_no_defaults_and_keeps_unknown_keys_for_resolve_to_reject():
    schema = struct_of(_Search)
    assert schema.decode({"query": "x", "nope": 1}) == {"query": "x", "nope": 1}
    with pytest.raises(SchemaTypeError, match=r"unexpected key\(s\): nope"):
        schema.resolve(schema.decode({"query": "x", "nope": 1}))


def test_decode_returns_a_fresh_tree_and_never_touches_the_one_it_is_given():
    """README guarantees; docs/decode.md 'Fresh trees'."""
    schema = struct_of(_Search)
    wire = {"query": "x", "page": {"size": 30}, "tags": ["a"]}
    before = deepcopy(wire)

    decoded = schema.decode(wire)
    assert wire == before
    assert decoded["page"] is not wire["page"]
    assert decoded["tags"] is not wire["tags"]


# README guarantees; docs/contract.md.
def test_to_dict_is_json_serializable_deterministic_and_owned_by_the_caller():
    schema = struct_of(_Search)
    document = schema.to_dict()

    assert json.dumps(document) == json.dumps(struct_of(_Search).to_dict())
    assert json.loads(json.dumps(document)) == document
    assert document["v"] == 1 and document["kind"] == "struct"

    document["defs"]["structs"].clear()
    document["v"] = 99
    assert schema.to_dict() == struct_of(_Search).to_dict()


def test_a_signature_document_names_the_function_and_carries_its_params():
    def upload(document: str, page: _Page = _Page()):
        """Upload a document."""

    written = signature_of(upload).to_dict()
    assert written["kind"] == "signature"
    assert written["name"] == "upload"
    assert written["doc"] == "Upload a document."
    assert [p["name"] for p in written["params"]] == ["document", "page"]
    assert json.dumps(written)


def test_no_implementation_object_reaches_the_document():
    """docs/contract.md 'What never appears'."""
    @dataclass
    class Model:
        code: Annotated[str, Pattern(r"\d+", message="digits")]
        role: _Role = _Role.ADMIN
        tags: list[str] = field(default_factory=list)
        maybe: int | None = None

    document = struct_of(Model).to_dict()
    allowed = (dict, list, str, int, float, bool, type(None))
    stack = [document]
    while stack:
        current = stack.pop()
        assert type(current) in allowed, current
        if type(current) is dict:
            stack.extend(current.keys())
            stack.extend(current.values())
        elif type(current) is list:
            stack.extend(current)

    fields = {f["name"]: f for f in document["defs"]["structs"]["Model"]["fields"]}
    assert "default" not in fields["code"]          # MISSING is the absent key
    assert fields["maybe"]["default"] is None       # the default really is None
    assert fields["role"]["default"] == "ADMIN"     # the member name, not "admin"


@dataclass
class _Written:
    when: str | date = date(2024, 6, 1)
    limit: int | float = 10
    role: _Role = _Role.ADMIN
    # The discriminator rule is about a slot, not a field: the element of this
    # list names its own option exactly as the field above does.
    days: list[str | date] = field(default_factory=lambda: [date(2024, 6, 1)])
    # Options sharing a Python type keep the wrapper past decode, for build.
    terms: list[str] | list[int] = field(default_factory=list)


def test_a_written_default_is_valid_input_to_the_pipeline():
    """docs/contract.md: 'One portable language, written by to_dict and read by decode.'"""
    schema = struct_of(_Written)
    written = {f["name"]: f for f in
               schema.to_dict()["defs"]["structs"]["_Written"]["fields"]}
    served = schema.build({})

    for name in ("when", "limit", "role", "days", "terms"):
        expected = getattr(served, name)
        recovered = schema.build(schema.decode({name: written[name]["default"]}))
        assert getattr(recovered, name) == expected
        assert type(getattr(recovered, name)) is type(expected)

    assert written["days"]["default"] == [{"$type": "date", "$value": "2024-06-01"}]
    assert written["terms"]["default"] == {"$type": "list[str]", "$value": []}


@pytest.mark.parametrize("name, expected", [
    ("when", date(2024, 6, 1)), ("limit", 10), ("role", _Role.ADMIN),
    ("days", [date(2024, 6, 1)]),
])
def test_decode_alone_already_lands_on_the_value_where_build_needs_no_discriminator(
        name, expected):
    schema = struct_of(_Written)
    written = {f["name"]: f for f in
               schema.to_dict()["defs"]["structs"]["_Written"]["fields"]}
    recovered = schema.decode({name: written[name]["default"]})[name]
    assert recovered == expected and type(recovered) is type(expected)


# docs/restrictions.md "Duplicate discriminator name".
@pytest.mark.parametrize("hint, name", [
    (str | Enum("str", {"A": 1}), "str"),
    (date | Enum("date", {"A": 1}), "date"),
    (list[str] | Enum("list[str]", {"A": 1}), "list[str]"),
])
def test_two_options_may_not_share_one_discriminator_identity(hint, name):
    model = make_dataclass("Colliding", [("x", hint)])
    with pytest.raises(ValueError) as error:
        struct_of(model)
    assert str(error.value) == f"Field 'x': duplicate discriminator name(s): {name}"


class _Ordered(dict):
    pass


class _Listish(list):
    pass


def test_a_container_subclass_is_handed_back_untouched_rather_than_rebuilt():
    """docs/decode.md 'Fresh trees': rebuilding one as a plain dict would be
    decode turning a subclass into its base, and would make validation accept a
    tree it is supposed to reject."""
    schema = struct_of(_User)
    given = _Ordered(name="Ana", birthday="2000-05-17")

    decoded = schema.decode(given)
    assert decoded is given                      # not descended into, not rebuilt
    assert decoded["birthday"] == "2000-05-17"   # and so nothing was restored

    with pytest.raises(SchemaTypeError) as error:
        schema.resolve(decoded)
    assert str(error.value) == "expected dict, got _Ordered"


def test_a_list_subclass_is_neither_descended_into_nor_turned_into_a_list():
    model = make_dataclass("Days", [("days", list[date])])
    schema = struct_of(model)
    given = _Listish(["2026-08-08"])

    decoded = schema.decode({"days": given})["days"]
    assert decoded is given and type(decoded) is _Listish
    with pytest.raises(SchemaTypeError, match=r"days: expected list, got _Listish"):
        schema.build({"days": decoded})


class _Colliding:
    """A key that hashes like a reserved one and raises when compared to it."""

    def __hash__(self):
        return hash("$type")

    def __eq__(self, other):
        raise AssertionError("a non-string key must never be compared")


@pytest.mark.parametrize("key", [1, True, None, (1, 2), 2.5, _Colliding()],
                         ids=["int", "bool", "none", "tuple", "float", "colliding"])
def test_a_dict_carrying_a_non_string_key_is_never_routed(key):
    """decode has to be total, and asking whether a foreign key matches a
    reserved one would run that key's own __eq__ on a hash collision."""
    model = make_dataclass("Held", [("v", str | date)])
    schema = struct_of(model)

    payload = {key: 1, "$value": 2}
    assert schema.decode({"v": payload}) == {"v": payload}
    assert schema.decode({key: 1, "v": "x"}) == {key: 1, "v": "x"}


@dataclass
class _Cash:
    amount: int


@dataclass
class _Card:
    number: str


def test_a_wrapper_is_not_consumed_on_a_field_whose_options_are_dataclasses():
    """Two dataclasses are told apart by an inline $type, so the wrapper names
    nothing here and is an ordinary foreign dictionary."""
    model = make_dataclass("Paid", [("by", _Cash | _Card)])
    schema = struct_of(model)
    wrapper = {"$type": "_Cash", "$value": {"amount": 1}}

    assert schema.decode({"by": wrapper}) == {"by": wrapper}
    with pytest.raises(SchemaTypeError, match=r"by: unexpected key\(s\): \$value"):
        schema.build({"by": wrapper})


def test_an_inline_discriminator_is_decoded_where_it_routes_and_ignored_where_it_cannot():
    both = struct_of(make_dataclass("Either", [("x", _Cash | _Card)]))
    assert both.decode({"x": {"$type": "_Cash", "amount": 1}}) == {
        "x": {"$type": "_Cash", "amount": 1}}
    # An unknown variant names no option, so nothing below it is decoded.
    assert both.decode({"x": {"$type": "Nope", "amount": 1}}) == {
        "x": {"$type": "Nope", "amount": 1}}

    # With a single dataclass option there is nothing to discriminate, so $type
    # is an ordinary unexpected key — docs/build.md.
    one = struct_of(make_dataclass("Only", [("x", _Cash)]))
    assert one.decode({"x": {"$type": "_Cash", "amount": 1}}) == {
        "x": {"$type": "_Cash", "amount": 1}}
    with pytest.raises(SchemaTypeError, match=r"x: unexpected key\(s\): \$type"):
        one.build({"x": {"$type": "_Cash", "amount": 1}})


def _every_union_of(names, sizes):
    pool = {
        "int": int, "float": float, "str": str, "bool": bool, "date": date,
        "time": time, "none": type(None), "role": _Role, "other": _OtherRole,
        "file": _File, "url": _Url, "list_str": list[str], "list_int": list[int],
        "list_date": list[date],
    }
    for size in sizes:
        for combination in combinations(names, size):
            hint = pool[combination[0]]
            for name in combination[1:]:
                hint = hint | pool[name]
            try:
                yield combination, struct_of(
                    make_dataclass("Union", [("v", hint)])).fields[0].shape
            except (TypeError, ValueError):
                continue


def test_every_option_build_needs_a_wrapper_for_also_needs_one_to_be_decoded():
    """`_decode_wrapped` keeps a wrapper by looking it up among the portable
    options; an option validation wraps but decode does not would silently have
    its payload left undecoded. The two sets are computed apart, so the
    containment is asserted rather than assumed."""
    names = ["int", "float", "str", "bool", "date", "time", "none", "role",
             "other", "file", "url", "list_str", "list_int", "list_date"]
    checked = 0
    for combination, shapes in _every_union_of(names, (2, 3)):
        wrapped = _wrapped_options(shapes)
        portable = _portable_options(shapes)
        for option in wrapped:
            assert any(option is candidate for candidate in portable), combination
        checked += 1
    assert checked > 300


def test_options_sharing_a_python_type_are_always_two_or_more_lists():
    """docs/contract.md and docs/decode.md tell a reader that the wrapper survives
    decode exactly where the slot holds two or more `list` options. Nothing else
    can share a Python type and still be distinguishable."""
    names = ["int", "float", "str", "bool", "date", "time", "none", "role",
             "other", "file", "url", "list_str", "list_int", "list_date"]
    seen_wrapped = False
    for combination, shapes in _every_union_of(names, (2, 3)):
        lists = sum(1 for shape in shapes if isinstance(shape, List))
        assert bool(_wrapped_options(shapes)) is (lists >= 2), combination
        seen_wrapped |= lists >= 2
    assert seen_wrapped


def test_a_dataclass_and_an_enum_of_one_name_use_different_discriminators():
    """docs/restrictions.md: they never compete for one discriminator."""
    shirt_struct = make_dataclass("Shirt", [("size", int)])
    shirt_enum = Enum("Shirt", {"M": 1})
    model = make_dataclass("Order", [("item", shirt_struct | shirt_enum)])

    document = struct_of(model).to_dict()
    assert document["defs"]["structs"]["Shirt"]["name"] == "Shirt"
    assert document["defs"]["enums"]["Shirt"]["members"] == ["M"]

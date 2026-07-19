"""Union options must compile to distinct types; None is a valid list item."""

from dataclasses import dataclass, field, make_dataclass
from typing import Annotated, Literal

import pytest

from pytypehint import Max, Min, struct_of


def _compile(hint):
    return struct_of(make_dataclass("C", [("x", hint)]))


# ------------------------------------------------- field-level collisions


def test_annotated_and_bare_option_collide_on_the_field():
    """docs/restrictions.md, 'Duplicate option types in a union': 'Field 'x': duplicate option types in shape'."""
    with pytest.raises(ValueError) as error:
        _compile(Annotated[int, Min(0)] | int)

    assert str(error.value) == "Field 'x': duplicate option types in shape"


def test_two_annotated_options_collide_on_the_field():
    """docs/restrictions.md: 'atoms narrow a type, they do not create one'."""
    with pytest.raises(ValueError) as error:
        _compile(Annotated[int, Min(0)] | Annotated[int, Max(9)])

    assert str(error.value) == "Field 'x': duplicate option types in shape"


def test_literal_collides_with_its_base_type_on_the_field():
    """docs/restrictions.md: '`Literal` counts as its base type, so `Literal["a", "b"] | str` collides'."""
    with pytest.raises(ValueError) as error:
        _compile(Literal["a", "b"] | str)

    assert str(error.value) == "Field 'x': duplicate option types in shape"


def test_two_list_options_are_told_apart_by_their_identity():
    """docs/restrictions.md: two options sharing a runtime type compile when their identities differ."""
    f = _compile(list[int] | list[str]).fields[0]

    assert [s.option_id() for s in f.shape] == ["list[int]", "list[str]"]


def test_two_identical_list_options_still_collide_on_the_field():
    """docs/restrictions.md: 'atoms narrow a type, they do not create one' — inside the item too."""
    with pytest.raises(ValueError) as error:
        _compile(list[Annotated[int, Min(0)]] | list[Annotated[int, Max(9)]])

    assert str(error.value) == "Field 'x': duplicate option types in shape"


def test_distinct_types_compile():
    """docs/restrictions.md: 'Every option of a union must compile to a distinct type' — these are."""
    f = _compile(int | str).fields[0]

    assert [s.pytype for s in f.shape] == [int, str]


# ---------------------------------------------- list-item collisions (3e)


def test_literal_and_str_items_name_both_options_and_the_way_out():
    """docs/restrictions.md, 'Duplicate option types in a union': the list-item collision names both options and the way out."""
    with pytest.raises(ValueError) as error:
        _compile(list[Literal["a", "b"] | str])

    assert str(error.value) == (
        "list items: Literal['a', 'b'] and str both compile to str — merge them "
        "into one option, or give each variant a dataclass and route with $type")


def test_two_literal_items_collide_naming_both():
    """docs/restrictions.md: two Literal options still compile to one base type."""
    with pytest.raises(ValueError) as error:
        _compile(list[Literal["a"] | Literal["b"]])

    assert str(error.value) == (
        "list items: Literal['a'] and Literal['b'] both compile to str — merge them "
        "into one option, or give each variant a dataclass and route with $type")


def test_two_annotated_items_collide_naming_both():
    """docs/restrictions.md: 'atoms narrow a type, they do not create one' — inside a list too."""
    with pytest.raises(ValueError) as error:
        _compile(list[Annotated[int, Min(0)] | Annotated[int, Max(9)]])

    assert str(error.value) == (
        "list items: Annotated[int, Min(value=0, exclusive=False)] and "
        "Annotated[int, Max(value=9, exclusive=False)] both compile to int — "
        "merge them into one option, or give each variant a dataclass and route with $type")


def test_mixed_items_as_one_option_is_the_documented_way_out():
    """docs/restrictions.md: 'Mixed items that are genuinely one field become one option: `list[int | str]`'."""
    struct = _compile(list[int | str])

    assert struct.build({"x": [1, "a", 2]}).x == [1, "a", 2]


def test_exclusive_variants_as_dataclasses_is_the_other_way_out():
    """docs/restrictions.md: 'Alternatives that are genuinely exclusive become dataclasses and route by name with `$type`'."""
    @dataclass
    class Fast:
        budget: int

    @dataclass
    class Safe:
        budget: int

    @dataclass
    class Plan:
        modes: list[Fast | Safe] = field(default_factory=list)

    built = struct_of(Plan).build({"modes": [
        {"$type": "Fast", "budget": 1},
        {"$type": "Safe", "budget": 2},
    ]})

    assert built == Plan(modes=[Fast(budget=1), Safe(budget=2)])


def test_hand_built_list_shape_still_reports_by_shape():
    """docs/restrictions.md: 'List.item has duplicate option types' — the schema-level message for a hand-built List."""
    from pytypehint import Int, List

    with pytest.raises(ValueError) as error:
        List(item=(Int(min=Min(0)), Int(max=Max(9))))

    assert str(error.value) == "List.item has duplicate option types"


# ------------------------------------------------------- None as list item


def test_none_is_a_valid_list_item_option():
    """docs/vocabulary.md: '`None` is a valid item option: `list[int | None]` accepts `None` holes as values'."""
    struct = _compile(list[int | None])

    assert struct.build({"x": [1, None, 2]}).x == [1, None, 2]


def test_none_holes_survive_resolve():
    """docs/vocabulary.md: 'A `None` item is data, not field optionality'."""
    struct = _compile(list[int | None])

    assert struct.resolve({"x": [None, 1]}) == {"x": [None, 1]}


def test_a_wrong_item_type_still_reports_its_index():
    """README, 'Guarantees': 'Errors retain the complete field and list-index path'."""
    struct = _compile(list[int | None])

    with pytest.raises(TypeError) as error:
        struct.build({"x": [1, "no"]})

    assert str(error.value) == "x: [1]: expected int | NoneType, got str"


def test_bare_none_list_is_rejected():
    """docs/vocabulary.md: '`list[None]` alone remains rejected'."""
    with pytest.raises(TypeError) as error:
        _compile(list[None])

    assert str(error.value) == "List.item cannot be NoneShape"


def test_none_item_is_not_field_optionality():
    """docs/vocabulary.md: 'A `None` item is data, not field optionality' — the field itself is still required."""
    struct = _compile(list[int | None])

    with pytest.raises(TypeError) as error:
        struct.build({})

    assert str(error.value) == "missing key(s): x"


# ----------------------------------------------------------------- fail fast


def test_validation_reports_only_the_first_violation():
    """docs/philosophy.md, 'Validation fails fast': 'The first violation is reported and validation stops. There is no error list'."""
    @dataclass
    class C:
        a: Annotated[int, Max(10)] = 0
        b: Annotated[int, Max(10)] = 0

    with pytest.raises(ValueError) as error:
        struct_of(C).build({"a": 99, "b": 99})

    # One coordinate, one reason — 'b' is never mentioned.
    assert str(error.value) == "a: too large: 99, maximum 10"
    assert error.value.path == ("a",)


def test_a_wrapper_can_collect_every_failure_itself():
    """docs/philosophy.md: 'The wrapper holds the compiled schema, so it can walk the fields itself and collect as many failures as it wants'."""
    @dataclass
    class C:
        a: Annotated[int, Max(10)] = 0
        b: Annotated[int, Max(10)] = 0

    struct = struct_of(C)
    data = {"a": 99, "b": 98}

    collected = {}
    for f in struct.fields:
        try:
            f._check_value_data(data[f.name])
        except (TypeError, ValueError) as e:
            collected[f.name] = str(e)

    assert collected == {"a": "too large: 99, maximum 10",
                         "b": "too large: 98, maximum 10"}

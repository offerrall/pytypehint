"""Unions whose options share one runtime input type.

`list[str] | list[int]` is a valid Python annotation, and both options arrive as
a `list`. The value alone cannot say which option it is, so the caller says it:
`{"$type": "list[str]", "$value": [...]}`. The wrapper is required only where
routing by exact type is ambiguous — see docs/restrictions.md and docs/build.md.
"""

import pickle
from dataclasses import dataclass, field, make_dataclass
from typing import Annotated

import pytest

from pytypehint import (
    Int, List, Max, Min, SchemaTypeError, SchemaValueError, Str, signature_of,
    struct_of,
)


@dataclass
class Shirt:
    size: str


@dataclass
class Mug:
    capacity: int


def _compile(hint, default=None):
    spec = ("x", hint) if default is None else ("x", hint, default)
    return struct_of(make_dataclass("C", [spec]))


def _wrap(option, value):
    return {"$type": option, "$value": value}


# --------------------------------------------------------------- compilation


def test_options_sharing_a_runtime_type_compile_when_identities_differ():
    """docs/restrictions.md: a shared runtime type is not a collision by itself."""
    f = _compile(list[str] | list[int]).fields[0]

    assert [s.option_id() for s in f.shape] == ["list[str]", "list[int]"]
    assert [s.pytype for s in f.shape] == [list, list]


@pytest.mark.parametrize("hint, option_ids", [
    (int | str, ["int", "str"]),
    (list[str] | list[int], ["list[str]", "list[int]"]),
    (list[list[str]] | list[list[int]], ["list[list[str]]", "list[list[int]]"]),
    (None | list[str], ["None", "list[str]"]),
    (list[str] | list[int] | None, ["list[str]", "list[int]", "None"]),
    (list[str | int], ["list[str | int]"]),
    (Shirt | Mug, ["Shirt", "Mug"]),
    (list[Shirt] | list[Mug], ["list[Shirt]", "list[Mug]"]),
])
def test_option_identity_is_stable_readable_and_free_of_typing_prefixes(hint, option_ids):
    """docs/restrictions.md, 'Option identity': the name a discriminator can use."""
    f = _compile(hint).fields[0]

    assert [s.option_id() for s in f.shape] == option_ids


def test_options_that_stay_indistinguishable_are_rejected_at_compilation():
    """docs/restrictions.md: same runtime type and same identity leaves nothing to name."""
    with pytest.raises(ValueError) as error:
        _compile(list[Annotated[int, Min(0)]] | list[Annotated[int, Max(9)]])

    assert str(error.value) == "Field 'x': duplicate option types in shape"


def test_hand_built_indistinguishable_list_items_are_rejected():
    """docs/restrictions.md: 'List.item has duplicate option types', by shape."""
    with pytest.raises(ValueError) as error:
        List(item=(List(item=(Str(),)), List(item=(Str(),))))

    assert str(error.value) == "List.item has duplicate option types"


def test_hand_built_distinguishable_list_items_compile():
    shape = List(item=(List(item=(Str(),)), List(item=(Int(),))))

    assert shape.option_id() == "list[list[str] | list[int]]"


# --------------------------------------------------- list[str | int] is not
# --------------------------------------------------- list[str] | list[int]


def test_a_union_item_routes_each_element_and_needs_no_discriminator():
    """docs/vocabulary.md: `list[str | int]` is one list of mixed items."""
    schema = _compile(list[str | int])

    assert schema.build({"x": ["a", 1, "b", 2]}).x == ["a", 1, "b", 2]


def test_a_union_of_lists_selects_one_option_for_the_whole_list():
    """docs/vocabulary.md: `list[str] | list[int]` is two exclusive lists."""
    schema = _compile(list[str] | list[int])

    assert schema.build({"x": _wrap("list[str]", ["a", "b"])}).x == ["a", "b"]
    assert schema.build({"x": _wrap("list[int]", [1, 2])}).x == [1, 2]


def test_the_two_annotations_do_not_share_a_semantics():
    """The mixed list is legal for one hint and illegal for the other, and vice versa."""
    item_union = _compile(list[str | int])
    list_union = _compile(list[str] | list[int])

    assert item_union.build({"x": ["a", 1]}).x == ["a", 1]
    with pytest.raises(TypeError):
        list_union.build({"x": _wrap("list[str]", ["a", 1])})

    with pytest.raises(TypeError):
        item_union.build({"x": _wrap("list[str]", ["a"])})
    assert list_union.build({"x": _wrap("list[str]", ["a"])}).x == ["a"]


# --------------------------------------------------------- resolve and build


def test_resolve_preserves_the_wrapper_and_build_consumes_it():
    """docs/resolve.md: resolve validates and returns the data it was given."""
    schema = _compile(list[str] | list[int])
    data = {"x": _wrap("list[int]", [1, 2])}

    assert schema.resolve(data) == data
    assert schema.build(data).x == [1, 2]


def test_an_empty_list_is_valid_under_the_named_option_only():
    """An empty list is evidence of nothing; the discriminator still decides."""
    schema = _compile(list[str] | list[int])

    assert schema.build({"x": _wrap("list[str]", [])}).x == []
    assert schema.build({"x": _wrap("list[int]", [])}).x == []


def test_nested_lists_route_through_their_own_identity():
    schema = _compile(list[list[str]] | list[list[int]])

    assert schema.build({"x": _wrap("list[list[int]]", [[1], [2, 3]])}).x == [[1], [2, 3]]


def test_a_list_of_ambiguous_lists_wraps_every_element():
    schema = _compile(list[list[str] | list[int]])

    built = schema.build({"x": [_wrap("list[str]", ["a"]), _wrap("list[int]", [1])]})
    assert built.x == [["a"], [1]]


def test_three_options_offer_all_three_names():
    schema = _compile(list[str] | list[int] | list[bool])

    assert schema.build({"x": _wrap("list[bool]", [True])}).x == [True]
    with pytest.raises(ValueError) as error:
        schema.build({"x": _wrap("list[float]", [])})
    assert error.value.leaf == (
        "not a choice: 'list[float]', expected one of "
        "('list[str]', 'list[int]', 'list[bool]')")


def test_none_beside_ambiguous_options_still_routes_by_type():
    schema = _compile(list[str] | list[int] | None, field(default=None))

    assert schema.build({"x": None}).x is None
    assert schema.build({"x": _wrap("list[str]", ["a"])}).x == ["a"]
    assert schema.build({}).x is None


def test_none_before_a_single_list_needs_no_wrapper():
    """The discriminator is required only where routing is ambiguous."""
    schema = _compile(None | list[str], field(default=None))

    assert schema.build({"x": ["a"]}).x == ["a"]
    assert schema.build({"x": None}).x is None


def test_lists_are_rebuilt_fresh_and_not_shared_with_the_input():
    schema = _compile(list[str] | list[int])
    payload = ["a"]

    built = schema.build({"x": _wrap("list[str]", payload)})
    assert built.x == payload
    assert built.x is not payload


# ---------------------------------------------------------- wrapper failures


def test_a_bare_value_names_the_options_and_the_way_out():
    schema = _compile(list[str] | list[int])

    with pytest.raises(SchemaTypeError) as error:
        schema.resolve({"x": ["a"]})

    assert error.value.path == ("x",)
    assert error.value.leaf == (
        'ambiguous list: field accepts list[str] | list[int] — wrap it as '
        '{"$type": ..., "$value": ...} naming the option')


def test_a_missing_discriminator_names_the_options():
    schema = _compile(list[str] | list[int])

    with pytest.raises(SchemaTypeError) as error:
        schema.resolve({"x": {"$value": ["a"]}})

    assert error.value.leaf == (
        'ambiguous value: field accepts list[str] | list[int] — wrap it as '
        '{"$type": ..., "$value": ...} naming the option')


def test_an_unknown_discriminator_is_a_value_error_at_its_own_coordinate():
    schema = _compile(list[str] | list[int])

    with pytest.raises(SchemaValueError) as error:
        schema.resolve({"x": _wrap("list[float]", [])})

    assert error.value.path == ("x", "$type")
    assert error.value.leaf == (
        "not a choice: 'list[float]', expected one of ('list[str]', 'list[int]')")


def test_a_non_string_discriminator_is_a_type_error_at_its_own_coordinate():
    schema = _compile(list[str] | list[int])

    with pytest.raises(SchemaTypeError) as error:
        schema.resolve({"x": _wrap(1, [])})

    assert error.value.path == ("x", "$type")
    assert error.value.leaf == "expected str, got int"


def test_a_wrapper_without_a_value_reports_the_missing_key():
    schema = _compile(list[str] | list[int])

    with pytest.raises(SchemaTypeError) as error:
        schema.resolve({"x": {"$type": "list[str]"}})

    assert error.value.path == ("x",)
    assert error.value.leaf == "missing key(s): $value"


def test_the_wrapper_accepts_no_other_key():
    schema = _compile(list[str] | list[int])

    with pytest.raises(SchemaTypeError) as error:
        schema.resolve({"x": {"$type": "list[str]", "$value": [], "extra": 1, "also": 2}})

    assert error.value.leaf == "unexpected key(s): also, extra"


def test_the_discriminator_is_checked_before_the_payload():
    """docs/build.md: the discriminator selects an option, then the payload is validated."""
    schema = _compile(list[str] | list[int])

    with pytest.raises(SchemaValueError) as error:
        schema.resolve({"x": _wrap("list[float]", ["not an int either"])})

    assert error.value.path == ("x", "$type")


def test_a_payload_of_the_wrong_type_reports_under_value():
    schema = _compile(list[str] | list[int])

    with pytest.raises(SchemaTypeError) as error:
        schema.resolve({"x": _wrap("list[str]", "abc")})

    assert error.value.path == ("x", "$value")
    assert error.value.leaf == "expected list, got str"


def test_a_wrong_item_reports_its_index_under_value():
    schema = _compile(list[str] | list[int])

    with pytest.raises(SchemaTypeError) as error:
        schema.resolve({"x": _wrap("list[str]", ["a", 2])})

    assert error.value.path == ("x", "$value", 1)
    assert error.value.leaf == "expected str, got int"
    assert str(error.value) == "x: $value: [1]: expected str, got int"


def test_a_deep_index_keeps_the_complete_path():
    schema = _compile(list[list[str]] | list[list[int]])

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": _wrap("list[list[int]]", [[1], [2, "3"]])})

    assert error.value.path == ("x", "$value", 1, 1)
    assert str(error.value) == "x: $value: [1]: [1]: expected int, got str"


def test_a_wrapper_error_survives_pickling():
    schema = _compile(list[str] | list[int])

    with pytest.raises(SchemaValueError) as error:
        schema.resolve({"x": _wrap("list[float]", [])})

    revived = pickle.loads(pickle.dumps(error.value))
    assert type(revived) is SchemaValueError
    assert revived.path == error.value.path
    assert revived.leaf == error.value.leaf
    assert str(revived) == str(error.value)


def test_an_unambiguous_option_does_not_accept_the_wrapper():
    """The wrapper exists to break a tie; without one it is just a foreign dict."""
    schema = _compile(list[str])

    with pytest.raises(SchemaTypeError) as error:
        schema.resolve({"x": _wrap("list[str]", ["a"])})

    assert error.value.leaf == "expected list, got dict"


# ------------------------------------------------------------------ defaults


def test_a_default_needs_no_discriminator_and_is_certified():
    """docs/defaults.md: a default is a value, not input data."""
    schema = _compile(list[str] | list[int], field(default_factory=lambda: ["a"]))

    assert schema.build({}).x == ["a"]
    assert schema.resolve({}) == {"x": ["a"]}


def test_an_empty_default_is_accepted_and_served_fresh():
    schema = _compile(list[str] | list[int], field(default_factory=list))

    first = schema.build({}).x
    second = schema.build({}).x
    assert first == second == []
    assert first is not second


def test_a_default_matching_no_option_is_rejected_at_compilation():
    with pytest.raises(SchemaValueError) as error:
        _compile(list[str] | list[int], field(default_factory=lambda: ["a", 1]))

    assert str(error.value) == (
        "x: default: matches no option: list[str] | list[int]")


def test_a_default_of_the_wrong_type_still_reports_the_type():
    with pytest.raises(SchemaTypeError) as error:
        _compile(list[str] | list[int], field(default=3))

    assert str(error.value) == "x: default: expected list, got int"


def test_dataclass_list_defaults_are_rematerialized_per_serving():
    schema = struct_of(make_dataclass("C", [
        ("x", list[Shirt] | list[Mug], field(default_factory=lambda: [Mug(1)]))]))

    first = schema.build({})
    second = schema.build({})
    assert first.x == second.x == [Mug(1)]
    assert first.x[0] is not second.x[0]


# ------------------------------------------------------- dataclass neighbours


def test_dataclass_options_keep_the_inline_discriminator():
    """docs/build.md: the dataclass format of 0.0.2 is unchanged."""
    schema = _compile(Shirt | Mug)
    data = {"x": {"$type": "Mug", "capacity": 3}}

    assert schema.resolve(data) == data
    assert schema.build(data).x == Mug(3)


def test_dataclass_items_inside_a_list_keep_the_inline_discriminator():
    schema = _compile(list[Shirt | Mug])

    built = schema.build({"x": [{"$type": "Shirt", "size": "M"},
                                {"$type": "Mug", "capacity": 3}]})
    assert built.x == [Shirt("M"), Mug(3)]


def test_lists_of_dataclasses_select_one_option_for_the_whole_list():
    schema = _compile(list[Shirt] | list[Mug])

    built = schema.build({"x": _wrap("list[Shirt]", [{"size": "M"}, {"size": "L"}])})
    assert built.x == [Shirt("M"), Shirt("L")]


def test_a_list_of_dataclasses_reports_the_field_under_value_and_index():
    schema = _compile(list[Shirt] | list[Mug])

    with pytest.raises(SchemaTypeError) as error:
        schema.build({"x": _wrap("list[Mug]", [{"capacity": 1}, {"capacity": "x"}])})

    assert error.value.path == ("x", "$value", 1, "capacity")


def test_a_dataclass_option_and_ambiguous_lists_coexist():
    """A dict is a payload unless it carries the reserved "$value" key."""
    schema = _compile(Shirt | list[str] | list[int])

    assert schema.build({"x": {"size": "M"}}).x == Shirt("M")
    assert schema.build({"x": _wrap("list[int]", [1])}).x == [1]


def test_a_dataclass_instance_is_still_rejected_beside_ambiguous_lists():
    schema = _compile(Shirt | list[str] | list[int])

    with pytest.raises(SchemaTypeError) as error:
        schema.resolve({"x": Shirt("M")})

    assert error.value.leaf == "expected dict, got Shirt instance"


def test_duplicate_dataclass_names_are_still_rejected_at_compilation():
    first = make_dataclass("Same", [("a", int)])
    second = make_dataclass("Same", [("b", str)])

    with pytest.raises(ValueError) as error:
        struct_of(make_dataclass("Root", [("x", list[first] | list[second])]))

    assert str(error.value) == "Field 'x': duplicate option types in shape"


# ---------------------------------------------- signatures and recursion


def test_a_signature_parameter_takes_the_wrapper_too():
    def run(terms: list[str] | list[int], n: int = 1):
        return terms, n

    kwargs = signature_of(run).build({"terms": _wrap("list[int]", [1, 2])})

    assert kwargs == {"terms": [1, 2], "n": 1}
    assert run(**kwargs) == ([1, 2], 1)


@dataclass
class Node:
    name: str
    kids: "list[Node] | list[str]" = field(default_factory=list)


def test_a_recursive_shape_certifies_and_routes_after_its_graph_is_complete():
    """Certification is deferred for recursive graphs; the identity check waits with it."""
    schema = struct_of(Node)

    assert [s.option_id() for s in schema.fields[1].shape] == ["list[Node]", "list[str]"]
    assert schema.build({"name": "a"}) == Node("a", [])
    assert schema.build({"name": "a", "kids": _wrap("list[str]", ["x"])}) == Node("a", ["x"])
    assert schema.build(
        {"name": "a", "kids": _wrap("list[Node]", [{"name": "b"}])}
    ) == Node("a", [Node("b", [])])


def test_a_recursive_wrapper_error_keeps_the_whole_path():
    with pytest.raises(SchemaTypeError) as error:
        struct_of(Node).build({"name": "a", "kids": _wrap("list[Node]", [{"name": 1}])})

    assert error.value.path == ("kids", "$value", 0, "name")


# ------------------------------------------------- regressions of 0.0.2 hints


@pytest.mark.parametrize("hint, value", [
    (int | str, 3),
    (int | str, "hola"),
    (int | None, None),
    (list[int] | None, [1, 2]),
    (list[str | int], ["a", 1]),
    (list[int | None], [1, None]),
    (list[list[int]], [[1], [2]]),
])
def test_previously_supported_unions_still_route_without_a_discriminator(hint, value):
    schema = _compile(hint)

    assert schema.resolve({"x": value}) == {"x": value}
    assert schema.build({"x": value}).x == value

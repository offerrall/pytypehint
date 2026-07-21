"""Two behaviours that only surface off the input-data path.

`check_options_value` (src/pytypehint/validation.py) raises "matches no option"
when a value's runtime type is shared by several options but satisfies none.
The input-data path never reaches it — an ambiguous shared type is handled by
the `$type`/`$value` wrapper first — so the message only appears when a *value*
(a rematerialized default, or an already-constructed instance validated through
`Struct._check`) is routed. test_discriminated_wrapper.py pins the default case
("Field 'x': default matches no option"); this file pins the instance case.

The second half pins homonym enums as union options: two Enum classes that share
`__name__` route by their exact member type, because `duplicate_options` groups
by runtime type, not by identity. shapes.py: "two enums that share a class name
still route by their exact member type".
"""

from dataclasses import dataclass, make_dataclass
from enum import Enum

import pytest

from pytypehint import EnumShape, SchemaTypeError, SchemaValueError, struct_of
from pytypehint.shapes import duplicate_options


# --------------------------------- "matches no option" on instance validation ---
# `list[str] | list[int]` compiles (distinct identities). A value whose runtime
# type (list) is shared by both options but which satisfies neither — a mixed
# list — has no option, and instance validation says so.


def test_matches_no_option_surfaces_through_instance_validation():
    """src/pytypehint/validation.py: "matches no option" — reached by validating a *value* (an instance), not input data.

    Regression caught: this branch is unreachable from resolve/build (ambiguous
    shared types go through the wrapper). If check_options_value dropped the
    multi-candidate 'none accepts' branch, instance validation of a mixed list
    would silently pass.
    """
    @dataclass
    class C:
        x: list[str] | list[int]

    schema = struct_of(C)

    with pytest.raises(SchemaValueError) as error:
        schema._check(C(x=["a", 1]))

    assert error.value.path == ("x",)
    assert str(error.value) == "x: matches no option: list[str] | list[int]"


def test_matches_no_option_is_a_value_error_distinct_from_a_wrong_type():
    """docs/philosophy.md, 'Hints are exact': a shared runtime type that matches no option is a value failure; a foreign type is a type failure.

    Regression caught: collapsing these two into one exception class would blur
    the SchemaTypeError/SchemaValueError distinction the README promises.
    """
    @dataclass
    class C:
        x: list[str] | list[int]

    schema = struct_of(C)

    with pytest.raises(SchemaTypeError) as wrong_type:
        schema._check(C(x=42))
    assert wrong_type.value.leaf == "expected list, got int"


def test_matches_no_option_carries_the_nested_field_path():
    """errors.py: the leaf is prefixed at each level it is re-raised through — a nested field prepends its own coordinate.

    Regression caught: a nested instance failure that lost its outer field name
    would report ("x",) instead of ("inner","x").
    """
    @dataclass
    class Inner:
        x: list[str] | list[int]

    @dataclass
    class Outer:
        inner: Inner

    schema = struct_of(Outer)

    with pytest.raises(SchemaValueError) as error:
        schema._check(Outer(inner=Inner(x=["a", 1])))

    assert error.value.path == ("inner", "x")
    assert str(error.value) == "inner: x: matches no option: list[str] | list[int]"


def test_matches_no_option_carries_the_list_index_path():
    """docs/build.md: "Validation errors accumulate field names and list indexes" — including an index above a matches-no-option leaf.

    Regression caught: List._check not prefixing the item index would strip the
    [1] coordinate from this instance failure.
    """
    @dataclass
    class HasList:
        items: list[list[str] | list[int]]

    schema = struct_of(HasList)

    with pytest.raises(SchemaValueError) as error:
        schema._check(HasList(items=[["ok"], ["a", 1]]))

    assert error.value.path == ("items", 1)
    assert str(error.value) == "items: [1]: matches no option: list[str] | list[int]"


# ------------------------------------------------ homonym enums as union options ---
# Two Enum classes both named "Color". They share an option_id ("Color") but not
# a runtime type, so they are routable and compile.


def _homonym_enums():
    left = Enum("Color", {"RED": 1, "GREEN": 2})
    right = Enum("Color", {"YES": "y", "NO": "n"})
    return left, right


def test_homonym_enums_compile_as_distinct_options_despite_a_shared_identity():
    """shapes.py: "two enums that share a class name still route by their exact member type".

    Regression caught: an option_id collision (both "Color") would look like a
    duplicate to a naive check; the schema must key on runtime type and admit it.
    """
    left, right = _homonym_enums()
    schema = struct_of(make_dataclass("C", [("x", left | right)]))

    shapes = schema.fields[0].shape
    assert [s.option_id() for s in shapes] == ["Color", "Color"]
    assert [s.pytype for s in shapes] == [left, right]
    assert left is not right


def test_duplicate_options_groups_by_runtime_type_not_by_identity():
    """shapes.py, duplicate_options: options collide only when they share both a runtime type *and* an identity.

    Regression caught: if duplicate_options keyed on option_id alone (ignoring
    pytype), homonym enums would be wrongly rejected as duplicates — and the same
    enum twice would still (correctly) be caught, so this pins both directions.
    """
    left, right = _homonym_enums()

    assert duplicate_options((EnumShape(cls=left), EnumShape(cls=right))) is False
    assert duplicate_options((EnumShape(cls=left), EnumShape(cls=left))) is True


def test_homonym_enums_route_each_member_by_its_exact_class():
    """docs/vocabulary.md: "Enum values must be members of the exact enum class" — even when two enum options share a name.

    Regression caught: routing by class *name* instead of exact type would send
    a member of the right enum to the left option (or vice versa).
    """
    left, right = _homonym_enums()
    schema = struct_of(make_dataclass("C", [("x", left | right)]))

    assert schema.resolve({"x": left.RED}) == {"x": left.RED}
    assert schema.resolve({"x": right.YES}) == {"x": right.YES}


def test_a_foreign_value_names_the_shared_identity_once():
    """src/pytypehint/validation.py, accepted(): options sharing a runtime type name it once — homonym enums report "Color", not "Color | Color".

    Regression caught: dropping the dict.fromkeys dedup in accepted() would emit
    the duplicated name for a foreign value.
    """
    left, right = _homonym_enums()
    schema = struct_of(make_dataclass("C", [("x", left | right)]))

    with pytest.raises(SchemaTypeError) as error:
        schema.resolve({"x": 5})

    assert error.value.leaf == "expected Color, got int"


def test_homonym_enums_inside_a_list_route_each_element():
    """docs/vocabulary.md: "union-valued items are supported" — a list of two homonym enums routes each element by its exact member type.

    Regression caught: a list item router keyed on the enum name would misroute
    elements between the two same-named options.
    """
    left, right = _homonym_enums()
    schema = struct_of(make_dataclass("C", [("x", list[left | right])]))

    item_ids = [s.option_id() for s in schema.fields[0].shape[0].item]
    assert item_ids == ["Color", "Color"]

    built = schema.build({"x": [left.RED, right.YES, left.GREEN]})
    assert built.x == [left.RED, right.YES, left.GREEN]

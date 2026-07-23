"""Two behaviours that only surface off the input-data path.

`check_options_value` (src/pytypehint/validation.py) raises "matches no option"
when a value's runtime type is shared by several options but satisfies none.
The input-data path never reaches it — an ambiguous shared type is handled by
the `$type`/`$value` wrapper first — so the message only appears when a *value*
(a rematerialized default, or an already-constructed instance validated through
`Struct._check`) is routed. test_discriminated_wrapper.py pins the default case
("x: default: matches no option"); this file pins the instance case.

The second half pins homonym enums as union options. Two Enum classes that share
`__name__` route by their exact member type — `duplicate_options` groups by
runtime type, not identity, and never flags them. But the field still rejects the
pair at compile time: `option_id()` is the public identity every wrapper reads to
name an option, and two options that collapse to one identity are a defective
schema, the same defect `_check_discriminators` rejects for homonym dataclasses.
The rejection lives in `_check_discriminators`, not in `duplicate_options`; the
two are kept distinct on purpose (a struct and an enum of the same name never
share a `$type` and stay admissible).
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
# a runtime type. duplicate_options (which keys on runtime type) admits them, but
# the field's discriminator check rejects them: one public identity for two
# options is a defective schema, symmetric with homonym dataclasses.


def _homonym_enums():
    left = Enum("Color", {"RED": 1, "GREEN": 2})
    right = Enum("Color", {"YES": "y", "NO": "n"})
    return left, right


def test_homonym_enums_are_rejected_at_compilation():
    """structure.py, _check_discriminators: two enum options that share a class name collapse to one option_id and are rejected while compiling the field.

    Regression caught: dropping enums from the discriminator check would let a
    schema compile whose two "Color" options are indistinguishable by their public
    identity — the exact collision a wrapper cannot resolve.
    """
    left, right = _homonym_enums()

    with pytest.raises(
            ValueError,
            match=r"Field 'x': duplicate discriminator name\(s\): Color"):
        struct_of(make_dataclass("C", [("x", left | right)]))


def test_homonym_enums_inside_a_list_are_rejected_at_compilation():
    """structure.py, _check_discriminators: the check recurses into List items, so `list[E1 | E2]` of homonym enums is rejected one level down too.

    Regression caught: a check that stopped at the field's own shapes would admit
    the collision as long as it hid inside a list.
    """
    left, right = _homonym_enums()

    with pytest.raises(
            ValueError,
            match=r"Field 'x': duplicate discriminator name\(s\): Color"):
        struct_of(make_dataclass("C", [("x", list[left | right])]))


def test_duplicate_options_still_admits_homonym_enums_by_runtime_type():
    """shapes.py, duplicate_options: options collide there only when they share both a runtime type *and* an identity — the homonym rejection lives elsewhere.

    Regression caught: if the fix had moved the rejection into duplicate_options,
    it would key on option_id alone and wrongly report homonym enums as a
    *duplicate option type*; and the same enum twice must still be caught here.
    This pins that _check_discriminators, not duplicate_options, owns the rule.
    """
    left, right = _homonym_enums()

    assert duplicate_options((EnumShape(cls=left), EnumShape(cls=right))) is False
    assert duplicate_options((EnumShape(cls=left), EnumShape(cls=left))) is True


def test_non_homonym_enums_still_compile_and_route_by_exact_class():
    """docs/vocabulary.md: two enums with distinct names route by their exact member type — the fix touches only the name collision, nothing else.

    Regression caught: an over-broad rejection keyed on runtime type or on being
    an enum at all would break ordinary two-enum unions.
    """
    left = Enum("Left", {"RED": 1, "GREEN": 2})
    right = Enum("Right", {"YES": "y", "NO": "n"})
    schema = struct_of(make_dataclass("C", [("x", left | right)]))

    assert [s.option_id() for s in schema.fields[0].shape] == ["Left", "Right"]
    assert schema.resolve({"x": left.RED}) == {"x": left.RED}
    assert schema.resolve({"x": right.YES}) == {"x": right.YES}
    assert schema.build({"x": left.GREEN}).x is left.GREEN


def test_a_homonym_dataclass_and_enum_do_not_collide():
    """structure.py, _check_discriminators: each kind guards its own identity namespace — a dataclass and an enum of the same name never share a `$type`, so the pair compiles.

    A struct arrives as a dict routed by "$type" = class name; an enum arrives as
    a member routed by exact type and never carries a "$type". Their identity
    spaces are disjoint, so a shared name is harmless. This pins the deliberate
    seam between the two namespaces.
    """
    dc = make_dataclass("Nom", [("a", int)])
    en = Enum("Nom", {"K": 1})
    schema = struct_of(make_dataclass("C", [("x", dc | en)]))

    # The struct is the only dataclass option, so it takes no discriminator.
    assert schema.resolve({"x": {"a": 3}}) == {"x": {"a": 3}}
    assert schema.resolve({"x": en.K}) == {"x": en.K}
    assert schema.build({"x": {"a": 3}}).x == dc(3)

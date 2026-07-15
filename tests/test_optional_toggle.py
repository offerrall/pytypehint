from dataclasses import dataclass
from typing import Annotated

import pytest

from pytypehint import OptionalToggle, signature_of, struct_of
from pytypehint.shapes import Int, NoneShape, Str


def test_atom_requires_exact_bool():
    with pytest.raises(TypeError, match="OptionalToggle.enabled must be bool, got int"):
        OptionalToggle(1)


@pytest.mark.parametrize("enabled", [True, False])
def test_toggle_transported(enabled):
    @dataclass
    class C:
        x: Annotated[int | None, OptionalToggle(enabled)] = None

    assert struct_of(C).fields[0].optional_toggle == OptionalToggle(enabled)


def test_signature_transport():
    def fn(x: Annotated[int | None, OptionalToggle(True)] = None):
        pass

    assert signature_of(fn).params[0].optional_toggle == OptionalToggle(True)


def test_no_mark_is_none():
    @dataclass
    class C:
        x: int | None = None

    assert struct_of(C).fields[0].optional_toggle is None


def test_mark_requires_optional_field():
    @dataclass
    class C:
        x: Annotated[int, OptionalToggle(False)] = 0

    with pytest.raises(TypeError, match=r"Field 'x': OptionalToggle requires an optional field"):
        struct_of(C)


def test_mark_on_list_item_rejected():
    @dataclass
    class C:
        x: list[Annotated[int | None, OptionalToggle(True)]]

    with pytest.raises(TypeError, match="field atoms cannot apply to list items"):
        struct_of(C)


def test_same_layer_last_toggle_wins():
    @dataclass
    class C:
        x: Annotated[int | None, OptionalToggle(True), OptionalToggle(False)] = None

    assert struct_of(C).fields[0].optional_toggle == OptionalToggle(False)


def test_outer_toggle_overrides_alias_layer():
    Opt = Annotated[int, OptionalToggle(True)]

    @dataclass
    class C:
        x: Annotated[Opt | None, OptionalToggle(False)] = None

    assert struct_of(C).fields[0].optional_toggle == OptionalToggle(False)


def test_conflicting_toggle_across_union_options_uses_generic_path():
    A = Annotated[int, OptionalToggle(True)]
    B = Annotated[str, OptionalToggle(False)]

    @dataclass
    class C:
        x: A | B | None = None

    with pytest.raises(TypeError, match="conflicting optionaltoggles across union options"):
        struct_of(C)


def test_toggle_does_not_change_resolution_or_validation():
    @dataclass
    class C:
        x: Annotated[int | None, OptionalToggle(False)] = 5

    s = struct_of(C)
    assert s.resolve({}) == {"x": 5}
    assert s.resolve({"x": None}) == {"x": None}


def test_fields_use_identity_equality():
    @dataclass
    class A:
        x: Annotated[int | None, OptionalToggle(True)] = None

    @dataclass
    class B:
        x: Annotated[int | None, OptionalToggle(False)] = None

    fa = struct_of(A).fields[0]
    fb = struct_of(B).fields[0]
    assert fa != fb


@dataclass
class _Tree:
    next: Annotated["_Tree | None", OptionalToggle(True)] = None


def test_recursive_and_multi_option_fields_transport_toggle():
    assert struct_of(_Tree).fields[0].optional_toggle == OptionalToggle(True)

    @dataclass
    class C:
        x: Annotated[int | str | None, OptionalToggle(True)] = None

    f = struct_of(C).fields[0]
    assert f.optional_toggle == OptionalToggle(True)
    assert {type(s) for s in f.shape} == {Int, Str, NoneShape}

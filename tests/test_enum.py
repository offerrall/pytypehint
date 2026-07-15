from dataclasses import dataclass, field
from enum import Enum, Flag, IntEnum, IntFlag, StrEnum
from typing import Annotated

import pytest

from pytypehint.atoms import Description, Label, Min, Placeholder
from pytypehint.bridge import signature_of, struct_of
from pytypehint.shapes import EnumShape, Int, NoneShape
from pytypehint.structure import Struct


class Role(Enum):
    ADMIN = "admin"
    VIEWER = "viewer"


class Other(Enum):
    ADMIN = "admin"
    VIEWER = "viewer"


class Color(StrEnum):
    RED = "red"
    BLUE = "blue"


class Size(IntEnum):
    SMALL = 1
    LARGE = 2


@dataclass
class Node:
    role: Role = Role.ADMIN
    next: "Node | None" = None


def test_enumshape_rejects_non_enum_class():
    with pytest.raises(TypeError, match="must be an Enum class"):
        EnumShape(cls=int)


def test_enumshape_rejects_non_class():
    with pytest.raises(TypeError, match="must be an Enum class"):
        EnumShape(cls=5)


def test_enumshape_rejects_empty_enum():
    class Empty(Enum):
        pass

    with pytest.raises(ValueError, match="no members"):
        EnumShape(cls=Empty)


def test_enumshape_rejects_flag():
    class Perm(Flag):
        A = 1

    with pytest.raises(TypeError, match="Flag enums are not supported"):
        EnumShape(cls=Perm)


def test_enumshape_rejects_intflag():
    class Perm(IntFlag):
        A = 1

    with pytest.raises(TypeError, match="Flag enums are not supported"):
        EnumShape(cls=Perm)


def test_basic_field_compiles_to_enumshape():
    @dataclass
    class C:
        role: Role

    (f,) = struct_of(C).fields
    assert f.shape == (EnumShape(cls=Role),)


def test_resolve_accepts_member():
    @dataclass
    class C:
        role: Role

    assert struct_of(C).resolve({"role": Role.ADMIN}) == {"role": Role.ADMIN}


def test_resolve_rejects_raw_string():
    @dataclass
    class C:
        role: Role

    with pytest.raises(TypeError, match="expected Role, got str"):
        struct_of(C).resolve({"role": "admin"})


def test_resolve_rejects_member_of_other_enum():
    @dataclass
    class C:
        role: Role

    with pytest.raises(TypeError, match="expected Role, got Other"):
        struct_of(C).resolve({"role": Other.ADMIN})


def test_signature_compiles_and_routes():
    def f(role: Role):
        return role

    sig = signature_of(f)
    assert sig.resolve({"role": Role.VIEWER}) == {"role": Role.VIEWER}
    with pytest.raises(TypeError, match="expected Role, got str"):
        sig.resolve({"role": "viewer"})


def test_default_by_reference():
    @dataclass
    class C:
        role: Role = Role.ADMIN

    out = struct_of(C).resolve({})
    assert out["role"] is Role.ADMIN


def test_invalid_default_fails_compilation():
    @dataclass
    class C:
        role: Role = "admin"

    with pytest.raises(TypeError, match="expected Role, got str"):
        struct_of(C)


def test_optional_enum():
    @dataclass
    class C:
        role: Role | None = None

    schema = struct_of(C)
    assert schema.fields[0].shape == (EnumShape(cls=Role), NoneShape())
    assert schema.resolve({"role": None}) == {"role": None}
    assert schema.resolve({"role": Role.ADMIN}) == {"role": Role.ADMIN}


def test_list_of_enum():
    @dataclass
    class C:
        roles: list[Role] = field(default_factory=list)

    schema = struct_of(C)
    assert schema.resolve({"roles": [Role.ADMIN]}) == {"roles": [Role.ADMIN]}
    with pytest.raises(TypeError, match=r"\[0\]: expected Role, got str"):
        schema.resolve({"roles": ["admin"]})


def test_union_with_int_routes():
    @dataclass
    class C:
        v: Role | int = 0

    schema = struct_of(C)
    assert schema.resolve({"v": 1}) == {"v": 1}
    assert schema.resolve({"v": Role.ADMIN}) == {"v": Role.ADMIN}


def test_strenum_compiles_to_enumshape():
    @dataclass
    class C:
        color: Color

    schema = struct_of(C)
    assert isinstance(schema.fields[0].shape[0], EnumShape)
    with pytest.raises(TypeError, match="expected Color, got str"):
        schema.resolve({"color": "red"})
    assert schema.resolve({"color": Color.RED}) == {"color": Color.RED}


def test_intenum_rejected_by_int_field():
    @dataclass
    class C:
        n: int = 0

    with pytest.raises(TypeError, match="expected int, got Size"):
        struct_of(C).resolve({"n": Size.SMALL})


def test_intenum_accepted_by_own_field():
    @dataclass
    class C:
        size: Size

    assert struct_of(C).resolve({"size": Size.SMALL}) == {"size": Size.SMALL}


def test_atoms_rejected_min():
    @dataclass
    class C:
        role: Annotated[Role, Min(0)]

    with pytest.raises(TypeError, match="unsupported metadata for enum"):
        struct_of(C)


def test_atoms_rejected_placeholder():
    @dataclass
    class C:
        role: Annotated[Role, Placeholder("x")]

    with pytest.raises(TypeError, match="unsupported metadata for enum"):
        struct_of(C)


def test_field_atoms_pass_through():
    @dataclass
    class C:
        role: Annotated[Role, Label("Role"), Description("User role")] = Role.ADMIN

    (f,) = struct_of(C).fields
    assert f.label == Label("Role")
    assert f.description == Description("User role")
    assert f.shape == (EnumShape(cls=Role),)


def test_structural_contents_match_but_fields_have_identity():
    @dataclass
    class A:
        role: Role

    @dataclass
    class B:
        role: Role

    a = struct_of(A).fields[0]
    b = struct_of(B).fields[0]
    assert a != b
    assert a.shape == b.shape
    assert EnumShape(cls=Role) == EnumShape(cls=Role)
    assert EnumShape(cls=Role) != EnumShape(cls=Other)


def test_dict_rejected():
    @dataclass
    class C:
        role: Role

    with pytest.raises(TypeError, match="expected Role, got dict"):
        struct_of(C).resolve({"role": {"name": "ADMIN"}})


def test_recursion_with_enum_field():
    schema = struct_of(Node)
    assert isinstance(schema, Struct)
    out = schema.resolve({"role": Role.VIEWER, "next": None})
    assert out == {"role": Role.VIEWER, "next": None}

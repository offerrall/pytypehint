from dataclasses import dataclass, field, InitVar
from typing import Annotated, ClassVar

import pytest

from pytypehint.atoms import Label, Max, Min
from pytypehint.bridge import struct_of
from pytypehint.shapes import Bool, Int, List, NoneShape
from pytypehint.structure import Field, Struct
from pytypehint.utils import MISSING


@dataclass
class Leaf:
    n: int = 0


@dataclass
class Branch:
    leaf: Leaf = field(default_factory=Leaf)


@dataclass
class Diamond:
    branch: Branch = field(default_factory=Branch)
    leaf: Leaf = field(default_factory=Leaf)


def test_diamond_is_not_a_cycle():
    s = struct_of(Diamond)
    assert len(s.fields) == 2
    s._check(Diamond())


def test_same_type_twice_side_by_side():
    @dataclass
    class Twins:
        a: Leaf = field(default_factory=Leaf)
        b: Leaf = field(default_factory=Leaf)

    s = struct_of(Twins)
    assert s.fields[0].shape[0] == s.fields[1].shape[0]
    s._check(Twins())


def test_same_type_in_list_and_field():
    @dataclass
    class Both:
        one: Leaf = field(default_factory=Leaf)
        many: list[Leaf] = field(default_factory=list)

    s = struct_of(Both)
    s._check(Both(many=[Leaf(1), Leaf(2)]))


@dataclass
class Base:
    a: int = 1
    b: bool = False


@dataclass
class Child(Base):
    c: Annotated[int, Min(value=0)] = 0


@dataclass
class Overriding(Base):
    a: Annotated[int, Max(value=9)] = 5


def test_inheritance_includes_parent_fields_in_order():
    s = struct_of(Child)
    assert [f.name for f in s.fields] == ["a", "b", "c"]
    assert s.fields[0].default == 1
    assert s.fields[2].shape[0] == Int(min=Min(value=0))


def test_inheritance_check():
    s = struct_of(Child)
    s._check(Child())
    s._check(Child(a=99, b=True, c=3))

    with pytest.raises(ValueError, match="c: too small"):
        s._check(Child(c=-1))


def test_override_keeps_position_and_takes_new_constraint():
    s = struct_of(Overriding)
    assert [f.name for f in s.fields] == ["a", "b"]
    assert s.fields[0].shape[0] == Int(max=Max(value=9))
    assert s.fields[0].default == 5

    with pytest.raises(ValueError, match="a: too large"):
        s._check(Overriding(a=99))


def test_grandchild():
    @dataclass
    class Grand(Child):
        d: bool = True

    s = struct_of(Grand)
    assert [f.name for f in s.fields] == ["a", "b", "c", "d"]
    s._check(Grand())


def test_init_false_rejected():
    @dataclass
    class C:
        a: int = 0
        b: int = field(init=False, default=0)

    with pytest.raises(TypeError, match="init=False"):
        struct_of(C)


def test_init_false_with_factory_rejected():
    @dataclass
    class C:
        a: int = 0
        computed: list[int] = field(init=False, default_factory=list)

    with pytest.raises(TypeError, match="init=False"):
        struct_of(C)


def test_initvar_rejected():
    @dataclass
    class C:
        a: int = 0
        token: InitVar[int] = 0

        def __post_init__(self, token):
            ...

    with pytest.raises(TypeError, match=r"^token: InitVar fields are not supported$"):
        struct_of(C)


def test_initvar_with_default_still_rejected():
    @dataclass
    class C:
        password: InitVar[str] = "x"

        def __post_init__(self, password):
            ...

    with pytest.raises(TypeError, match=r"^password: InitVar fields are not supported$"):
        struct_of(C)


def test_initvar_message_names_the_initvar_not_a_normal_field():
    @dataclass
    class C:
        a: int = 0
        secret: InitVar[int] = 0
        b: int = 1

        def __post_init__(self, secret):
            ...

    with pytest.raises(TypeError, match=r"^secret: InitVar fields are not supported$"):
        struct_of(C)


def test_initvar_in_nested_field_rejected_when_outer_compiles():
    @dataclass
    class Inner:
        salt: InitVar[int] = 0

        def __post_init__(self, salt):
            ...

    @dataclass
    class Outer:
        inner: Inner = field(default_factory=lambda: Inner())

    with pytest.raises(TypeError, match=r"^salt: InitVar fields are not supported$"):
        struct_of(Outer)


def test_post_init_without_initvar_compiles_fine():
    @dataclass
    class C:
        a: int = 0

        def __post_init__(self):
            ...

    s = struct_of(C)
    assert [f.name for f in s.fields] == ["a"]


def test_classvar_is_invisible():
    @dataclass
    class C:
        registry: ClassVar[int] = 0
        n: int = 1

    s = struct_of(C)
    assert [f.name for f in s.fields] == ["n"]


def test_empty_dataclass():
    @dataclass
    class Empty:
        pass

    s = struct_of(Empty)
    assert s.fields == ()
    s._check(Empty())


def test_empty_dataclass_nested():
    @dataclass
    class Empty:
        pass

    @dataclass
    class Holder:
        e: Empty = field(default_factory=Empty)

    s = struct_of(Holder)
    s._check(Holder())


def test_docstring_is_not_captured():
    @dataclass
    class C:
        """Una clase documentada."""
        n: int = 0

    s = struct_of(C)
    assert not hasattr(s, "doc")


def test_frozen_dataclass_works():
    @dataclass(frozen=True)
    class C:
        n: Annotated[int, Min(value=0)] = 0

    s = struct_of(C)
    s._check(C(n=5))
    with pytest.raises(ValueError, match="n: too small"):
        s._check(C(n=-1))


def test_kw_only_dataclass_works():
    @dataclass(kw_only=True)
    class C:
        n: int = 0
        b: bool = False

    s = struct_of(C)
    assert [f.name for f in s.fields] == ["n", "b"]
    s._check(C(n=1, b=True))


def test_deep_nesting_three_levels():
    @dataclass
    class L3:
        n: Annotated[int, Min(value=0)] = 0

    @dataclass
    class L2:
        l3: L3 = field(default_factory=L3)

    @dataclass
    class L1:
        l2: L2 = field(default_factory=L2)

    s = struct_of(L1)
    s._check(L1())
    assert s.fields[0].shape[0].fields[0].shape[0].fields[0].name == "n"


def test_check_rejects_wrong_class():
    @dataclass
    class A:
        n: int = 0

    @dataclass
    class B:
        n: int = 0

    s = struct_of(A)
    with pytest.raises(TypeError, match="expected A, got B"):
        s._check(B())


def test_check_rejects_dict():
    @dataclass
    class C:
        n: int = 0

    with pytest.raises(TypeError, match="expected C, got dict"):
        struct_of(C)._check({"n": 0})


def test_check_rejects_subclass_instance():
    s = struct_of(Base)
    with pytest.raises(TypeError, match="expected Base, got Child"):
        s._check(Child())


def test_check_error_names_the_field():
    @dataclass
    class C:
        n: Annotated[int, Min(value=0)] = 0

    with pytest.raises(ValueError, match=r"^n: too small: -1"):
        struct_of(C)._check(C(n=-1))


def test_check_error_chains_through_nesting():
    @dataclass
    class Inner:
        level: Annotated[int, Min(value=0)] = 0

    @dataclass
    class Outer:
        inner: Inner = field(default_factory=Inner)

    with pytest.raises(ValueError, match=r"^inner: level: too small"):
        struct_of(Outer)._check(Outer(inner=Inner(level=-1)))


def test_check_error_chains_three_deep():
    @dataclass
    class L3:
        n: Annotated[int, Min(value=0)] = 0

    @dataclass
    class L2:
        l3: L3 = field(default_factory=L3)

    @dataclass
    class L1:
        l2: L2 = field(default_factory=L2)

    with pytest.raises(ValueError, match=r"^l2: l3: n: too small"):
        struct_of(L1)._check(L1(l2=L2(l3=L3(n=-1))))


def test_check_error_chains_through_list_of_structs():
    @dataclass
    class Item:
        n: Annotated[int, Min(value=0)] = 0

    @dataclass
    class Bag:
        items: list[Item] = field(default_factory=list)

    with pytest.raises(ValueError, match=r"^items: \[1\]: n: too small"):
        struct_of(Bag)._check(Bag(items=[Item(0), Item(-1)]))


def test_check_reports_first_bad_field():
    @dataclass
    class C:
        a: Annotated[int, Min(value=0)] = 0
        b: Annotated[int, Min(value=0)] = 0

    with pytest.raises(ValueError, match=r"^a: too small"):
        struct_of(C)._check(C(a=-1, b=-1))


def test_check_optional_struct_dispatch():
    @dataclass
    class Inner:
        n: Annotated[int, Min(value=0)] = 0

    @dataclass
    class Outer:
        inner: Inner | None = None

    s = struct_of(Outer)
    s._check(Outer())
    s._check(Outer(inner=Inner(n=1)))

    with pytest.raises(ValueError, match=r"^inner: n: too small"):
        s._check(Outer(inner=Inner(n=-1)))

    with pytest.raises(TypeError, match=r"^inner: expected Inner"):
        s._check(Outer(inner=5))


def test_check_missing_attribute():
    @dataclass
    class C:
        n: int

    c = C(n=0)
    del c.n
    with pytest.raises(AttributeError):
        struct_of(C)._check(c)


@dataclass
class Manual:
    n: int = 0


def test_manual_struct_ok():
    s = Struct(cls=Manual, fields=(Field(name="n", shape=(Int(),), default=0),))
    s._check(Manual())


CONSTRUCTION_ERRORS = [
    (lambda: Struct(cls=5, fields=()), TypeError, "must be a class"),
    (lambda: Struct(cls=Manual(), fields=()), TypeError, "must be a class"),
    (lambda: Struct(cls=Manual, fields=[]), TypeError, "must be a tuple of Field"),
    (lambda: Struct(cls=Manual, fields=(Int(),)), TypeError, "must be a tuple of Field"),
    (lambda: Struct(cls=Manual, fields=(
        Field(name="a", shape=(Int(),)), Field(name="a", shape=(Bool(),)),
    )), ValueError, "duplicate field names"),
]


@pytest.mark.parametrize("build, exc, match", CONSTRUCTION_ERRORS,
                         ids=range(len(CONSTRUCTION_ERRORS)))
def test_manual_construction_errors(build, exc, match):
    with pytest.raises(exc, match=match):
        build()


def test_struct_cls_need_not_be_a_dataclass():
    class Plain:
        def __init__(self):
            self.n = 5

    s = Struct(cls=Plain, fields=(Field(name="n", shape=(Int(),)),))
    s._check(Plain())


def test_struct_is_a_shape():
    s = Struct(cls=Manual, fields=(Field(name="n", shape=(Int(),), default=0),))
    List(item=(s,))._check([Manual(), Manual()])
    Field(name="x", shape=(s, NoneShape()), default=None)._check_value(None)


def test_struct_equality_is_identity():
    a = Struct(cls=Manual, fields=(Field(name="n", shape=(Int(),), default=0),))
    b = Struct(cls=Manual, fields=(Field(name="n", shape=(Int(),), default=0),))
    c = Struct(cls=Manual, fields=(Field(name="n", shape=(Int(min=Min(value=0)),), default=0),))
    assert a != b
    assert a != c


def test_struct_with_no_fields():
    @dataclass
    class Empty:
        pass
    schema = struct_of(Empty)
    assert schema.fields == ()
    assert schema.resolve({}) == {}

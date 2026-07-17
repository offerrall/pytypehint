from dataclasses import FrozenInstanceError, dataclass, field
from typing import Annotated

import pytest

from pytypehint import Description, Label, Min, signature_of, struct_of
from pytypehint.shapes import Date, Float, Int, List, NoneShape, Shape, Time
from pytypehint.signature import Signature
from pytypehint.structure import Field, Struct


@dataclass
class C:
    n: int = 0


@dataclass
class Node:
    value: int = 0
    next: "Node | None" = None


def test_shape_subclass_must_declare_pytype():
    with pytest.raises(TypeError, match="must declare pytype"):
        class Bad(Shape):
            pass


def test_shape_base_check_not_implemented():
    class Ok(Shape):
        pytype = int

    with pytest.raises(NotImplementedError, match="must implement check"):
        Ok()._check(1)


def test_struct_eq_non_struct_is_not_equal():
    s = struct_of(C)
    assert (s == 5) is False
    assert s.__eq__(5) is NotImplemented


def test_struct_repr_incomplete():
    raw = Struct.__new__(Struct)
    assert repr(raw) == "Struct(<incomplete>)"


def test_struct_repr_complete():
    assert repr(struct_of(C)) == "Struct(C)"


def test_field_name_must_be_str():
    with pytest.raises(TypeError, match="Field.name must be str"):
        Field(name=5, shape=(Int(),))


def test_field_name_must_be_identifier():
    with pytest.raises(ValueError, match="Field.name must be an identifier"):
        Field(name="not a name", shape=(Int(),))


def test_field_shape_must_be_non_empty_tuple():
    with pytest.raises(TypeError, match="Field.shape must be a non-empty tuple"):
        Field(name="x", shape=())


def test_field_shape_must_be_tuple_not_list():
    with pytest.raises(TypeError, match="Field.shape must be a non-empty tuple"):
        Field(name="x", shape=[Int()])


def test_field_shape_entries_must_be_shapes():
    with pytest.raises(TypeError, match="is not a shape"):
        Field(name="x", shape=(5,))


def test_signature_name_must_be_str():
    with pytest.raises(TypeError, match="Signature.name must be str"):
        Signature(name=5)


def test_signature_name_must_be_identifier():
    with pytest.raises(ValueError, match="Signature.name must be an identifier"):
        Signature(name="not valid")


def test_shape_is_frozen():
    with pytest.raises(FrozenInstanceError):
        Int().min = None


def test_struct_is_frozen():
    s = struct_of(C)
    with pytest.raises(FrozenInstanceError):
        s.fields = ()


def test_field_is_frozen():
    f = Field(name="x", shape=(Int(),))
    with pytest.raises(FrozenInstanceError):
        f.name = "y"


def test_resolve_does_not_mutate_input():
    data = {"n": 5}
    struct_of(C).resolve(data)
    assert data == {"n": 5}


def test_struct_hash_is_by_cls():
    assert isinstance(hash(struct_of(C)), int)


def test_recursive_struct_equal_across_independent_compiles():
    assert struct_of(Node) != struct_of(Node)


def test_signature_instance_default_reconstructed_fresh():
    # 0.1.0: rematerialization (doctrine item 1) — instance defaults reconstruct
    # through their own constructor per resolve.
    @dataclass
    class Cfg:
        n: int = 0

    c = Cfg()

    def fn(cfg: Cfg = c):
        ...

    got = signature_of(fn).resolve({})["cfg"]
    assert got is not c
    assert got == c


def test_union_value_type_mismatch_lists_accepted_types():
    @dataclass
    class M:
        v: Annotated[int, Min(0)] | str = 0

    with pytest.raises(TypeError, match=r"expected int \| str, got float"):
        struct_of(M).resolve({"v": 1.5})


def test_field_label_must_be_label():
    with pytest.raises(TypeError, match="Field.label must be Label"):
        Field(name="x", shape=(Int(),), label="not a label")


def test_field_description_must_be_description():
    with pytest.raises(TypeError, match="Field.description must be Description"):
        Field(name="x", shape=(Int(),), description="nope")


def test_field_accepts_label_and_description():
    f = Field(name="x", shape=(Int(),), label=Label("X"), description=Description("d"))
    assert f.label == Label("X")


def test_field_default_list_materialized_to_list():
    # 0.1.0: certified product (design constraint) — field.default is the
    # materialized list, not a frozen tuple.
    f = Field(name="xs", shape=(List(item=(Int(),)),), default=[1, 2, 3])
    assert type(f.default) is list
    assert f.default == [1, 2, 3]


def test_field_shape_entry_none_shape_alone_rejected():
    with pytest.raises(TypeError, match="None must be accompanied"):
        Field(name="x", shape=(NoneShape(),))


def test_struct_cls_must_be_class():
    with pytest.raises(TypeError, match="Struct.cls must be a class"):
        Struct(cls=5, fields=())


def test_struct_fields_must_be_tuple_of_field():
    with pytest.raises(TypeError, match="must be a tuple of Field"):
        Struct(cls=C, fields=(5,))


def test_struct_rejects_duplicate_field_names():
    with pytest.raises(ValueError, match="duplicate field names"):
        Struct(cls=C, fields=(Field(name="a", shape=(Int(),)),
                              Field(name="a", shape=(Int(),))))


def test_signature_doc_must_be_str_or_none():
    with pytest.raises(TypeError, match="Signature.doc must be str or None"):
        Signature(name="f", doc=5)


def test_signature_params_must_be_tuple_of_field():
    with pytest.raises(TypeError, match="must be a tuple of Field"):
        Signature(name="f", params=(5,))


def test_signature_rejects_duplicate_param_names():
    with pytest.raises(ValueError, match="duplicate parameter names"):
        Signature(name="f", params=(Field(name="a", shape=(Int(),)),
                                    Field(name="a", shape=(Int(),))))


def test_signature_of_rejects_lambda():
    with pytest.raises(TypeError, match="lambdas have no usable name"):
        signature_of(lambda x: x)


def test_signature_of_rejects_var_positional():
    def f(*args: int):
        ...

    with pytest.raises(TypeError, match="variadic parameters"):
        signature_of(f)


def test_signature_of_rejects_var_keyword():
    def f(**kwargs: int):
        ...

    with pytest.raises(TypeError, match="variadic parameters"):
        signature_of(f)


def test_signature_of_rejects_positional_only():
    def f(x: int, /):
        ...

    with pytest.raises(TypeError, match="positional-only parameters are not supported"):
        signature_of(f)


def test_signature_of_rejects_missing_hint():
    def f(a):
        ...

    with pytest.raises(TypeError, match="missing type hint"):
        signature_of(f)


def test_signature_of_rejects_non_function():
    with pytest.raises(TypeError, match="expected a plain function"):
        signature_of(42)


def test_struct_of_rejects_instance():
    with pytest.raises(TypeError, match="expected a dataclass type"):
        struct_of(C())


def test_struct_of_rejects_non_dataclass():
    # 0.1.0: doctrine item 7 — non-dataclass class gets its own message.
    with pytest.raises(TypeError, match="int is not a dataclass — add @dataclass"):
        struct_of(int)


@pytest.mark.parametrize("factory", [
    lambda: Int(min=Min(0)),
    lambda: Float(),
    lambda: Date(),
    lambda: Time(),
    lambda: List(item=(Int(),)),
])
def test_shapes_are_frozen(factory):
    shape = factory()
    with pytest.raises(FrozenInstanceError):
        shape.min = None


def test_signature_is_frozen():
    def f(a: int = 0):
        ...

    sig = signature_of(f)
    with pytest.raises(FrozenInstanceError):
        sig.name = "g"


def test_struct_equals_itself():
    s = struct_of(C)
    assert s == s
    assert s != struct_of(C)

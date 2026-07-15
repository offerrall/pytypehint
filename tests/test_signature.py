from dataclasses import dataclass, field
from functools import partial
from typing import Annotated, Optional

import pytest

from pytypehint.atoms import Label, Max, Min
from pytypehint.bridge import signature_of, struct_of
from pytypehint.shapes import Bool, Int, List, NoneShape, Shape
from pytypehint.signature import Signature
from pytypehint.structure import Field, Struct
from pytypehint.utils import MISSING


def test_simple_function():
    def fn(a: int, b: bool = True):
        ...

    sig = signature_of(fn)
    assert sig.name == "fn"
    assert sig.doc is None
    assert [p.name for p in sig.params] == ["a", "b"]
    assert sig.params[0].shape == (Int(),)
    assert sig.params[0].default is MISSING
    assert sig.params[1].shape == (Bool(),)
    assert sig.params[1].default is True


def test_doc_is_captured():
    def fn(a: int):
        """Suma cosas."""
        ...

    assert signature_of(fn).doc == "Suma cosas."


def test_return_annotation_is_ignored():
    def fn(a: int) -> str:
        ...

    sig = signature_of(fn)
    assert [p.name for p in sig.params] == ["a"]


def test_no_parameters():
    def fn():
        ...

    assert signature_of(fn).params == ()


def test_annotated_splits_type_and_field_atoms():
    def fn(n: Annotated[int, Min(value=0), Label(value="N")] = 5):
        ...

    (p,) = signature_of(fn).params
    assert p.shape == (Int(min=Min(value=0)),)
    assert p.label == Label(value="N")
    assert p.default == 5


def test_union_with_none():
    def fn(x: int | None = None):
        ...

    (p,) = signature_of(fn).params
    assert p.shape == (Int(), NoneShape())


def test_optional_alias():
    def fn(x: Optional[int] = None):
        ...

    (p,) = signature_of(fn).params
    assert p.shape == (Int(), NoneShape())


def test_list_of_int():
    def fn(ns: list[int]):
        ...

    (p,) = signature_of(fn).params
    assert p.shape == (List(item=(Int(),)),)


def test_list_with_bounds():
    def fn(ns: Annotated[list[Annotated[int, Min(value=0)]], Min(value=1), Max(value=3)]):
        ...

    (p,) = signature_of(fn).params
    assert p.shape == (List(item=(Int(min=Min(value=0)),), min=Min(value=1), max=Max(value=3)),)


@dataclass
class Cfg:
    volume: Annotated[int, Max(value=100)] = 50


def test_dataclass_parameter():
    def fn(cfg: "Cfg | None" = None):
        ...

    (p,) = signature_of(fn).params
    assert p.shape[0].cls is Cfg
    assert repr(p.shape[0].fields) == repr((
        Field(name="volume", shape=(Int(max=Max(value=100)),), default=50),))


@dataclass
class Inner:
    n: int = 0


@dataclass
class Outer:
    inner: Inner = field(default_factory=Inner)


def test_nested_dataclass_parameter():
    def fn(o: "Outer | None" = None):
        ...

    (p,) = signature_of(fn).params
    struct = p.shape[0]
    assert struct.cls is Outer
    assert struct.fields[0].shape[0].cls is Inner


@dataclass
class RecNode:
    value: Annotated[int, Min(value=0)] = 0
    child: "RecNode | None" = None


def test_recursive_dataclass_parameter():
    def fn(node: "RecNode | None" = None):
        ...

    (p,) = signature_of(fn).params
    struct = p.shape[0]
    assert struct.cls is RecNode
    assert struct.fields[1].shape[0] is struct


def test_keyword_only_is_accepted():
    def fn(*, a: int = 0):
        ...

    (p,) = signature_of(fn).params
    assert p.name == "a"
    assert p.default == 0


def test_rejects_var_positional():
    def fn(*args: int):
        ...

    with pytest.raises(TypeError, match=r"args: variadic parameters"):
        signature_of(fn)


def test_rejects_var_keyword():
    def fn(**kwargs: int):
        ...

    with pytest.raises(TypeError, match=r"kwargs: variadic parameters"):
        signature_of(fn)


def test_rejects_positional_only():
    def fn(a: int, /):
        ...

    with pytest.raises(TypeError, match=r"a: positional-only"):
        signature_of(fn)


def test_rejects_missing_hint():
    def fn(a):
        ...

    with pytest.raises(TypeError, match=r"a: missing type hint"):
        signature_of(fn)


def test_accepts_list_default():
    def fn(x: list[int] = [1, 2]):
        ...

    (p,) = signature_of(fn).params
    assert p.default == [1, 2]            # 0.1.0: certified product is a list, not a frozen tuple


def test_accepts_dataclass_instance_default():
    default = Cfg()

    def fn(cfg: "Cfg | None" = default):
        ...

    (p,) = signature_of(fn).params
    # 0.1.0: rematerialization (doctrine item 1) — an instance default reconstructs
    # through its own constructor, so the certified product equals but is not the original.
    assert p.default is not default
    assert p.default == default


def test_rejects_dict_default_via_vocabulary():
    def fn(x: dict[str, int] = {}):
        ...

    with pytest.raises(TypeError, match="unsupported type"):
        signature_of(fn)


def test_rejects_set_default_via_vocabulary():
    def fn(x: set[int] = set()):
        ...

    with pytest.raises(TypeError, match="unsupported type"):
        signature_of(fn)


def test_rejects_default_out_of_range():
    def fn(n: Annotated[int, Min(value=10)] = 5):
        ...

    with pytest.raises(ValueError, match="too small"):
        signature_of(fn)


def test_rejects_type_outside_vocabulary():
    def fn(b: bytes):
        ...

    with pytest.raises(TypeError, match="unsupported type"):
        signature_of(fn)


def test_rejects_lambda():
    with pytest.raises(TypeError, match="lambdas have no usable name"):
        signature_of(lambda x: x)


def test_unbound_method_via_class_redirects():
    class C:
        def m(self, n: int = 0) -> None:
            ...

    with pytest.raises(TypeError, match=r"^self: looks like an unbound method"):
        signature_of(C.m)


def test_cls_first_param_redirects_too():
    def factory(cls, n: int = 0):
        ...

    with pytest.raises(TypeError, match=r"^cls: looks like an unbound method"):
        signature_of(factory)


def test_hinted_first_self_is_a_free_function():
    # false-positive boundary: a hinted first `self` is a plain function, not a
    # method, so the redirect must NOT fire — it compiles.
    def f(self: int):
        ...

    (p,) = signature_of(f).params
    assert p.name == "self"
    assert p.shape == (Int(),)


def test_later_untyped_self_gets_the_normal_message():
    # the redirect is first-parameter-only: a `self` anywhere but position 0
    # falls through to the generic missing-hint error.
    def f(n: int, self) -> None:
        ...

    with pytest.raises(TypeError, match=r"^self: missing type hint$"):
        signature_of(f)


NOT_FUNCTIONS = [5, int, Cfg, Cfg(), "hola", None, len]


@pytest.mark.parametrize("obj", NOT_FUNCTIONS, ids=range(len(NOT_FUNCTIONS)))
def test_rejects_non_functions(obj):
    with pytest.raises(TypeError, match="expected a plain function"):
        signature_of(obj)


def test_struct_of_function_is_typeerror_now():
    def fn(a: int = 0):
        ...

    with pytest.raises(TypeError, match="expected a dataclass type"):
        struct_of(fn)


def test_signature_of_dataclass_is_typeerror():
    with pytest.raises(TypeError, match="expected a plain function"):
        signature_of(Cfg)


_GUIDANCE = "bound methods, partials and callable objects are not supported"


def test_bound_method_rejected_with_guidance():
    class Service:
        def search(self, q: str):
            ...

    with pytest.raises(TypeError, match=_GUIDANCE):
        signature_of(Service().search)


def test_partial_rejected_with_guidance():
    def named(q: str, extra: int):
        ...

    with pytest.raises(TypeError, match=_GUIDANCE):
        signature_of(partial(named, extra=1))


def test_callable_instance_rejected_with_guidance():
    class Callable:
        def __call__(self, q: str):
            ...

    with pytest.raises(TypeError, match=_GUIDANCE):
        signature_of(Callable())


def test_lambda_passes_the_function_gate():
    # a lambda IS a plain function (passes isfunction), so the improved gate must
    # not catch it — it is rejected later by the usable-name rule, never as a
    # "plain function" failure. This guards the gate against over-rejecting.
    with pytest.raises(TypeError, match="lambdas have no usable name"):
        signature_of(lambda q: q)


def _sig():
    def fn(a: int, b: bool = False):
        ...

    return signature_of(fn)


def test_check_all_present_valid():
    assert _sig().resolve({"a": 1, "b": True}) == {"a": 1, "b": True}


def test_check_absent_with_default_is_filled():
    assert _sig().resolve({"a": 1}) == {"a": 1, "b": False}


def test_check_absent_without_default():
    with pytest.raises(TypeError, match=r"^missing argument\(s\): a$"):
        _sig().resolve({"b": True})


def test_check_unexpected_argument():
    with pytest.raises(TypeError, match=r"unexpected argument\(s\): z"):
        _sig().resolve({"a": 1, "z": 9})


def test_check_non_string_argument_key():
    with pytest.raises(TypeError, match=r"^expected string keys, got int$"):
        _sig().resolve({1: "a"})


def test_check_several_unexpected_sorted():
    with pytest.raises(TypeError, match=r"unexpected argument\(s\): x, y, z"):
        _sig().resolve({"a": 1, "z": 1, "x": 1, "y": 1})


def test_check_constraint_violation_prefixed():
    def fn(n: Annotated[int, Min(value=0)]):
        ...

    with pytest.raises(ValueError, match=r"^n: too small: -1, minimum 0$"):
        signature_of(fn).resolve({"n": -1})


def test_check_wrong_type_prefixed():
    def fn(n: int):
        ...

    with pytest.raises(TypeError, match=r"^n: expected int, got str$"):
        signature_of(fn).resolve({"n": "x"})


def test_check_list_item_index_chained():
    def fn(ns: list[int]):
        ...

    with pytest.raises(TypeError, match=r"^ns: \[1\]: expected int"):
        signature_of(fn).resolve({"ns": [1, "x"]})


def test_dataclass_instance_input_rejected():
    def fn(cfg: "Cfg | None" = None):
        ...

    with pytest.raises(TypeError, match=r"^cfg: expected dict, got Cfg instance$"):
        signature_of(fn).resolve({"cfg": Cfg(volume=200)})


NON_DICTS = [[1, 2], None, Cfg(), "hola", 5]


@pytest.mark.parametrize("value", NON_DICTS, ids=range(len(NON_DICTS)))
def test_check_non_dict(value):
    with pytest.raises(TypeError, match="expected dict"):
        _sig().resolve(value)


def test_check_empty_on_signature_without_params():
    def fn():
        ...

    assert signature_of(fn).resolve({}) == {}


def test_check_absent_and_extra_unexpected_wins():
    with pytest.raises(TypeError, match=r"unexpected argument\(s\): z"):
        _sig().resolve({"z": 9})


def test_signature_is_not_a_shape():
    sig = _sig()
    assert not isinstance(sig, Shape)


def test_signature_cannot_be_a_field_shape():
    sig = _sig()
    with pytest.raises(TypeError):
        Field(name="x", shape=(sig,))


def test_signature_cannot_be_a_list_item():
    sig = _sig()
    with pytest.raises(TypeError):
        List(item=(sig,))


def test_same_dataclass_as_param_and_field_compile_independently():
    def fn(inner: "Inner | None" = None):
        ...

    @dataclass
    class Holder:
        inner: Inner = field(default_factory=Inner)

    from_param = signature_of(fn).params[0].shape[0]
    from_field = struct_of(Holder).fields[0].shape[0]
    assert from_param != from_field
    assert from_param.cls is from_field.cls is Inner


def test_manual_signature_ok():
    sig = Signature(name="f", params=(Field(name="a", shape=(Int(),)),))
    assert sig.name == "f"
    assert sig.resolve({"a": 1}) == {"a": 1}


def test_manual_name_not_identifier():
    with pytest.raises(ValueError, match="must be an identifier"):
        Signature(name="not a name")


def test_manual_duplicate_param_names():
    with pytest.raises(ValueError, match="duplicate parameter names"):
        Signature(name="f", params=(
            Field(name="a", shape=(Int(),)),
            Field(name="a", shape=(Bool(),)),
        ))


def test_manual_params_not_tuple_of_field():
    with pytest.raises(TypeError, match="must be a tuple of Field"):
        Signature(name="f", params=(Int(),))


def test_manual_doc_wrong_type():
    with pytest.raises(TypeError, match="doc must be str or None"):
        Signature(name="f", doc=5)


def test_signature_with_no_params():
    def action():
        return "done"
    sig = signature_of(action)
    assert sig.params == ()
    assert sig.resolve({}) == {}


def test_signature_no_params_rejects_extras():
    def action():
        return "done"
    sig = signature_of(action)
    with pytest.raises(TypeError, match="unexpected argument"):
        sig.resolve({"x": 1})


def test_signature_hashable_with_instance_default():
    @dataclass
    class Page:
        n: int = 0

    def f(page: Page = Page()):
        ...

    assert isinstance(hash(signature_of(f)), int)
    assert signature_of(f) != signature_of(f)

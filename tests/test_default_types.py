from dataclasses import dataclass, field
from typing import Annotated

import pytest


def test_non_frozen_dataclass_instance_default_is_rejected_by_python():
    @dataclass
    class Mutable:
        n: int = 1

    with pytest.raises(ValueError, match=r"mutable default .* for field value is not allowed"):
        @dataclass
        class Container:
            value: Mutable = Mutable()

from pytypehint import Min, signature_of, struct_of


def test_tuple_default_on_function_list_param_rejected():
    def f(tags: list[int] = (1, 2)):
        ...

    with pytest.raises(TypeError, match="Field 'tags': default expected list, got tuple"):
        signature_of(f)


def test_tuple_default_on_dataclass_list_field_rejected():
    @dataclass
    class C:
        tags: list[int] = (1, 2)

    with pytest.raises(TypeError, match="Field 'tags': default expected list, got tuple"):
        struct_of(C)


def test_tuple_default_factory_rejected():
    @dataclass
    class C:
        tags: list[int] = field(default_factory=lambda: (1, 2))

    with pytest.raises(TypeError, match="Field 'tags': default expected list, got tuple"):
        struct_of(C)


@dataclass
class Tree:
    children: "list[Tree]" = field(default_factory=lambda: ())


def test_recursive_tuple_default_rejected():
    with pytest.raises(TypeError, match="Field 'children': default expected list, got tuple"):
        struct_of(Tree)


def test_deep_inner_tuple_default_rejected_with_index_path():
    def f(m: list[list[int]] = [[1], (2,)]):
        ...

    with pytest.raises(TypeError, match=r"Field 'm': default \[1\]: expected list, got tuple"):
        signature_of(f)


def test_list_default_compiles_and_materializes():
    # 0.1.0: certified product (design constraint) — field.default is the
    # materialized list, not a frozen tuple.
    def f(tags: list[int] = [1, 2]):
        ...

    (param,) = signature_of(f).params
    assert param.default == [1, 2]
    assert type(param.default) is list


def test_list_default_resolves_fresh_each_call():
    def f(tags: list[int] = [1, 2]):
        ...

    sig = signature_of(f)
    a = sig.resolve({})["tags"]
    b = sig.resolve({})["tags"]
    assert a is not b
    assert a == b == [1, 2]


@dataclass
class Node:
    children: "list[Node]" = field(default_factory=list)


def test_recursive_valid_list_default_compiles_and_resolves():
    schema = struct_of(Node)
    assert schema.resolve({"children": [{"children": []}]}) == {"children": [{"children": []}]}


def test_float_field_with_int_default_still_fails():
    @dataclass
    class C:
        x: float = 1

    with pytest.raises(TypeError, match="Field 'x': default expected float, got int"):
        struct_of(C)


def test_dict_default_on_dataclass_field_still_fails():
    @dataclass
    class Inner:
        n: int = 0

    @dataclass
    class C:
        v: Inner = field(default_factory=lambda: {"n": 1})

    with pytest.raises(TypeError, match="Field 'v': default expected Inner, got dict"):
        struct_of(C)


def test_nested_list_of_dataclass_bad_default_reports_path():
    @dataclass
    class Cfg:
        retries: Annotated[int, Min(0)] = 0

    def f(cfgs: list[Cfg] = [Cfg(retries=-1)]):
        ...

    with pytest.raises(ValueError, match=r"Field 'cfgs': default \[0\]: retries: too small"):
        signature_of(f)

from dataclasses import dataclass, field
from typing import Annotated

import pytest

from pytypehint import Max, signature_of, struct_of


# Doctrine item 3: a recipe that passed certification but breaks its
# rematerializable promise later (non-deterministic) fails at the resolve/build
# where it does — wrapped with the field path and a `default` segment, re-raised
# as the original type for TypeError/ValueError, otherwise wrapped in ValueError.
# The served portion is validated on each resolve (a check pass, not the full
# compile-time certification), so a drifted-out-of-range value is caught too.


def test_valueerror_recipe_is_chained_with_default_segment():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) >= 2:
            raise ValueError("second call boom")
        return [1]

    @dataclass
    class C:
        opts: list[int] = field(default_factory=flaky)

    s = struct_of(C)                      # certification: call 1 → [1]
    assert s.fields[0].default == [1]
    with pytest.raises(ValueError, match=r"opts: default: second call boom"):
        s.resolve({})                     # call 2 → raises


def test_typeerror_recipe_preserves_type():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) >= 2:
            raise TypeError("second call type")
        return [1]

    @dataclass
    class C:
        opts: list[int] = field(default_factory=flaky)

    s = struct_of(C)
    with pytest.raises(TypeError, match=r"opts: default: second call type"):
        s.resolve({})


def test_other_exception_is_wrapped_in_valueerror():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) >= 2:
            raise RuntimeError("second call runtime")
        return [1]

    @dataclass
    class C:
        opts: list[int] = field(default_factory=flaky)

    s = struct_of(C)
    with pytest.raises(ValueError, match=r"opts: default: second call runtime"):
        s.resolve({})


def test_runtime_failure_is_chained_from_original():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) >= 2:
            raise RuntimeError("boom")
        return [1]

    @dataclass
    class C:
        opts: list[int] = field(default_factory=flaky)

    s = struct_of(C)
    with pytest.raises(ValueError) as info:
        s.resolve({})
    assert type(info.value.__cause__) is RuntimeError


def test_instance_reconstruction_failing_at_runtime_is_chained():
    # An instance default reconstructs through its own constructor. A flaky
    # __post_init__ passes certification (call 1) then raises on the first resolve
    # (call 2), surfacing on the default path.
    state = {"n": 0}

    @dataclass
    class Opt:
        def __post_init__(self):
            state["n"] += 1
            if state["n"] >= 2:
                raise ValueError("reconstruct boom")

    @dataclass
    class C:
        opt: Opt = field(default_factory=Opt)

    s = struct_of(C)                      # compile: Opt() → n=1, ok
    with pytest.raises(ValueError, match=r"opt: default: reconstruct boom"):
        s.resolve({})                     # n=2 → raises


def test_signature_argument_path_uses_the_same_default_segment():
    # The default-remat wrapping is identical on the signature (argument) path;
    # a captured list-of-instances default reconstructs its item, which is flaky.
    state = {"n": 0}

    @dataclass
    class Opt:
        def __post_init__(self):
            state["n"] += 1
            if state["n"] >= 3:           # def-time(1) + compile(2) succeed; resolve(3) raises
                raise ValueError("arg boom")

    seed = Opt()

    def g(items: list[Opt] = [seed]):
        ...

    sig = signature_of(g)
    with pytest.raises(ValueError, match=r"items: default: arg boom"):
        sig.resolve({})


def test_served_default_portion_is_validated():
    # TAREA 2: the served portion is checked on each resolve/build (a check pass,
    # not the full compile certification), so an impure recipe that drifts out of
    # range is caught here with a default segment.
    calls = []

    def growing():
        calls.append(1)
        return [len(calls)]

    @dataclass
    class C:
        opts: list[Annotated[int, Max(1)]] = field(default_factory=growing)

    s = struct_of(C)                      # call 1 → [1], certifies (item 1 <= 1)
    with pytest.raises(ValueError, match=r"opts: default: \[0\]: too large: 2, maximum 1"):
        s.resolve({})                     # call 2 → [2], item 2 > 1, rejected


def test_list_items_align_input_and_certified_default_routes():
    recipe = [[1, 2]]

    @dataclass
    class C:
        items: list[Annotated[int, Max(2)]] = field(
            default_factory=lambda: list(recipe[0]))

    schema = struct_of(C)
    assert schema.build({"items": [1, 2]}).items == [1, 2]
    assert schema.build({}).items == [1, 2]

    with pytest.raises(ValueError, match=r"^items: \[1\]: too large: 3, maximum 2$"):
        schema.build({"items": [1, 3]})

    recipe[0] = [1, 3]
    with pytest.raises(
            ValueError,
            match=r"^items: default: \[1\]: too large: 3, maximum 2$"):
        schema.build({})


def test_nested_struct_default_failure_has_outer_path():
    calls = []

    def growing():
        calls.append(1)
        return len(calls)

    @dataclass
    class Leaf:
        n: Annotated[int, Max(1)] = field(default_factory=growing)

    @dataclass
    class Root:
        leaf: Leaf

    schema = struct_of(Root)
    with pytest.raises(ValueError, match=r"leaf: n: default: too large: 2, maximum 1"):
        schema.build({"leaf": {}})


def test_nested_constructor_failure_is_raw():
    @dataclass
    class Explodes:
        n: int

        def __post_init__(self):
            raise ValueError("constructor raw")

    @dataclass
    class Container:
        item: Explodes

    with pytest.raises(ValueError, match=r"^constructor raw$"):
        struct_of(Container).build({"item": {"n": 1}})


def test_three_nested_struct_levels_accumulate_path():
    calls = []

    def growing():
        calls.append(1)
        return len(calls)

    @dataclass
    class Leaf:
        n: Annotated[int, Max(1)] = field(default_factory=growing)

    @dataclass
    class Middle:
        leaf: Leaf

    @dataclass
    class Root:
        middle: Middle

    schema = struct_of(Root)
    with pytest.raises(ValueError, match=r"middle: leaf: n: default: too large: 2, maximum 1"):
        schema.build({"middle": {"leaf": {}}})


def test_struct_inside_list_accumulates_index_path():
    calls = []

    def growing():
        calls.append(1)
        return len(calls)

    @dataclass
    class Item:
        n: Annotated[int, Max(1)] = field(default_factory=growing)

    @dataclass
    class Cart:
        items: list[Item]

    schema = struct_of(Cart)
    with pytest.raises(ValueError, match=r"items: \[0\]: n: default: too large: 2, maximum 1"):
        schema.build({"items": [{}]})

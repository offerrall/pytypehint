import pickle
from dataclasses import dataclass, field
from typing import Annotated

import pytest

from pytypehint import (
    Min, SchemaTypeError, SchemaValueError, signature_of, struct_of,
)


# Doctrine item 2: every recipe runs once at compile and its product is validated
# against the schema. A schema-invalid product reports a structured error whose
# path carries the field name and "default" (rendered `x: default: <leaf>`, the
# same format the runtime serving path produces); a recipe that RAISES during
# materialization gets the "could not be materialized" message instead.


def test_schema_invalid_default_value_fails_at_compile():
    @dataclass
    class C:
        n: Annotated[int, Min(0)] = -5

    with pytest.raises(ValueError, match=r"n: default: too small: -5, minimum 0"):
        struct_of(C)


def test_schema_invalid_default_type_fails_at_compile():
    @dataclass
    class C:
        x: float = 1

    with pytest.raises(TypeError, match=r"x: default: expected float, got int"):
        struct_of(C)


def test_nested_invalid_default_reports_path():
    @dataclass
    class Cfg:
        retries: Annotated[int, Min(0)] = 0

    def f(cfgs: list[Cfg] = [Cfg(retries=-1)]):
        ...

    with pytest.raises(ValueError, match=r"cfgs: default: \[0\]: retries: too small"):
        signature_of(f)


def test_factory_that_raises_reports_could_not_be_materialized():
    def boom():
        raise RuntimeError("nope")

    @dataclass
    class C:
        ns: list[int] = field(default_factory=boom)

    with pytest.raises(TypeError, match=r"Field 'ns': default could not be materialized: nope"):
        struct_of(C)


def test_could_not_be_materialized_is_chained_from_the_original():
    def boom():
        raise RuntimeError("nope")

    @dataclass
    class C:
        ns: list[int] = field(default_factory=boom)

    with pytest.raises(TypeError) as info:
        struct_of(C)
    assert type(info.value.__cause__) is RuntimeError


# --- certification through the deferred (recursive) path ---
# (recursive dataclasses live at module scope so the forward refs resolve)


@dataclass
class Node:
    v: int = 0
    kids: "list[Node]" = field(default_factory=list)


@dataclass
class BadTree:
    kids: "list[BadTree]" = field(default_factory=lambda: ())


def test_recursive_valid_default_certifies_and_compiles():
    s = struct_of(Node)
    assert s.fields[1].default == []


def test_recursive_invalid_default_fails_through_deferred_path():
    # kids: list[BadTree] is a not-ready recursive shape, so its default is
    # certified in the deferred pass — a tuple product is rejected there, same message.
    with pytest.raises(TypeError, match=r"kids: default: expected list, got tuple"):
        struct_of(BadTree)


# --- compile-time certification keeps the structured error contract ---
# The README promises `path` and `leaf` travel as data; certification must honour
# it in compile-time too, not degrade the whole line into the leaf. The path uses
# clean coordinates (field name, "default", sub-path) and renders identically to
# the runtime serving path (`_resolve_fields`).


def test_compile_time_cert_error_carries_field_and_default_in_the_path():
    @dataclass
    class C:
        n: Annotated[int, Min(0)] = -5

    with pytest.raises(SchemaValueError) as error:
        struct_of(C)

    assert error.value.path == ("n", "default")
    assert error.value.leaf == "too small: -5, minimum 0"
    assert str(error.value) == "n: default: too small: -5, minimum 0"


def test_compile_time_cert_error_keeps_the_wrong_type_as_a_type_error():
    @dataclass
    class C:
        x: float = 1

    with pytest.raises(SchemaTypeError) as error:
        struct_of(C)

    assert error.value.path == ("x", "default")
    assert error.value.leaf == "expected float, got int"
    assert str(error.value) == "x: default: expected float, got int"


def test_nested_compile_time_cert_error_keeps_the_sub_path():
    @dataclass
    class Cfg:
        retries: Annotated[int, Min(0)] = 0

    def f(cfgs: list[Cfg] = [Cfg(retries=-1)]):
        ...

    with pytest.raises(SchemaValueError) as error:
        signature_of(f)

    assert error.value.path == ("cfgs", "default", 0, "retries")
    assert error.value.leaf == "too small: -1, minimum 0"
    assert str(error.value) == "cfgs: default: [0]: retries: too small: -1, minimum 0"


def test_compile_time_cert_error_survives_pickle_with_path_and_leaf():
    @dataclass
    class C:
        n: Annotated[int, Min(0)] = -5

    with pytest.raises(SchemaValueError) as error:
        struct_of(C)

    revived = pickle.loads(pickle.dumps(error.value))

    assert revived.path == ("n", "default")
    assert revived.leaf == "too small: -5, minimum 0"
    assert str(revived) == "n: default: too small: -5, minimum 0"

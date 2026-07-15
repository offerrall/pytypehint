"""InitVar and init=False are rejected; ClassVar is not a field at all.

bridge reads these off the resolved type hints, which are public typing API. It
used to reach for dataclasses._FIELD_INITVAR and Field._field_type — CPython
privates — and the canaries guarding that dependency went away with it.
"""

import sys
import types
from dataclasses import InitVar, dataclass, field

import pytest

from pytypehint import struct_of


# ----------------------------------------------------------- observable rule


def test_initvar_field_is_rejected():
    """docs/restrictions.md, 'Dataclass InitVar or init=False': 'x: InitVar fields are not supported'."""
    @dataclass
    class C:
        x: InitVar[int]

    with pytest.raises(TypeError) as error:
        struct_of(C)

    assert str(error.value) == "x: InitVar fields are not supported"


def test_initvar_beside_regular_fields_is_rejected():
    """docs/restrictions.md: 'A schema field must both enter the constructor and remain on the instance'."""
    @dataclass
    class C:
        n: int = 1
        x: InitVar[int] = 2

        def __post_init__(self, x):
            self.n += x

    with pytest.raises(TypeError) as error:
        struct_of(C)

    assert str(error.value) == "x: InitVar fields are not supported"


def test_initvar_report_names_the_first_field_alphabetically():
    """docs/restrictions.md fixes a single '<name>: InitVar fields are not supported' line, so the report must be deterministic."""
    @dataclass
    class C:
        b: InitVar[int] = 1
        a: InitVar[int] = 2

        def __post_init__(self, b, a):
            pass

    with pytest.raises(TypeError) as error:
        struct_of(C)

    assert str(error.value) == "a: InitVar fields are not supported"


def test_init_false_field_is_rejected():
    """docs/restrictions.md, same section: 'x: init=False fields are not supported'."""
    @dataclass
    class C:
        x: int = field(default=1, init=False)

    with pytest.raises(TypeError) as error:
        struct_of(C)

    assert str(error.value) == "x: init=False fields are not supported"


# ------------------------------------- regression: hints, not CPython privates


def test_classvar_is_not_a_schema_field():
    """docs/restrictions.md, 'Dataclass InitVar or init=False': only fields that enter the constructor and stay on the instance become schema fields; ClassVar does neither."""
    from typing import ClassVar

    @dataclass
    class C:
        n: int = 1
        registry: ClassVar[dict] = {}
        label: ClassVar[str] = "c"

    struct = struct_of(C)

    assert [f.name for f in struct.fields] == ["n"]
    assert struct.build({"n": 2}) == C(n=2)


def test_classvar_beside_initvar_still_reports_only_the_initvar():
    """docs/restrictions.md: ClassVar is invisible to the schema, so it must not be mistaken for the unsupported InitVar."""
    from typing import ClassVar

    @dataclass
    class C:
        n: int = 1
        registry: ClassVar[dict] = {}
        seed: InitVar[int] = 2

        def __post_init__(self, seed):
            pass

    with pytest.raises(TypeError) as error:
        struct_of(C)

    assert str(error.value) == "seed: InitVar fields are not supported"


def test_initvar_is_detected_through_deferred_annotations():
    """docs/restrictions.md: the rule holds however the annotation is spelled — get_type_hints resolves a string InitVar to the same object."""
    # A real module: get_type_hints resolves a string annotation through
    # sys.modules[cls.__module__], which a bare exec namespace would not provide.
    # Registered before exec: @dataclass itself resolves the string annotation
    # through sys.modules[cls.__module__] while the class is being created.
    module = types.ModuleType("_deferred_initvar_fixture")
    sys.modules[module.__name__] = module
    try:
        exec(
            "from __future__ import annotations\n"
            "from dataclasses import dataclass, InitVar\n"
            "@dataclass\n"
            "class C:\n"
            "    n: int = 1\n"
            "    seed: InitVar[int] = 2\n"
            "    def __post_init__(self, seed): pass\n",
            module.__dict__,
        )
        with pytest.raises(TypeError) as error:
            struct_of(module.C)
    finally:
        del sys.modules[module.__name__]

    assert str(error.value) == "seed: InitVar fields are not supported"

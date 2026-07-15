from dataclasses import field

import pytest

from pytypehint import signature_of


# I11 / doctrine item 6: field() is dataclass syntax. A function parameter's
# default is written directly — it is fresh through the schema either way.


def test_field_with_plain_default_in_function_is_rejected():
    def fn(x: int = field(default=1)):
        ...

    with pytest.raises(
        TypeError,
        match=r"x: field\(\) is dataclass syntax; in functions write the default directly",
    ):
        signature_of(fn)


def test_field_with_factory_default_in_function_is_rejected():
    def fn(xs: list[int] = field(default_factory=list)):
        ...

    with pytest.raises(TypeError, match=r"xs: field\(\) is dataclass syntax"):
        signature_of(fn)


def test_message_names_the_offending_parameter():
    def fn(a: int, b: str = field(default="x")):
        ...

    with pytest.raises(TypeError, match=r"^b: field\(\) is dataclass syntax"):
        signature_of(fn)

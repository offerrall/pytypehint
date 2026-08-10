"""Shared test setup.

The only thing here is a guard against `typing`'s subscription cache leaking
between modules. `Annotated[...]` is memoised process-wide by the equality of its
arguments, and atoms compare by value: `Min(0)`, `Min(0.0)` and `Min(-0.0)` are
one key. So the first module to write `Annotated[int, Min(-0.0)]` makes every
later `Annotated[int, Min(0)]` in the process hand back the float — and the shape
refuses it with `Int.min: expected int, got float`, in a module that never wrote
a float. Clearing the cache between modules keeps each one honest.
"""

import typing

import pytest


@pytest.fixture(autouse=True, scope="module")
def _clear_typing_caches():
    yield
    for clear in typing._cleanups:
        clear()

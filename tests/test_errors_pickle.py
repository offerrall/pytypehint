"""Schema errors survive pickle and copy with their structure intact."""

import copy
import pickle
from dataclasses import dataclass, field
from typing import Annotated

import pytest

from pytypehint import Max, SchemaTypeError, SchemaValueError, struct_of


@dataclass(frozen=True)
class Page:
    size: Annotated[int, Max(100)] = 20


@dataclass
class Search:
    query: str
    page: Page = Page()
    tags: list[int] = field(default_factory=list)


def _nested_error():
    """The README's own failure: 'page: size: too large: 500, maximum 100'."""
    with pytest.raises(SchemaValueError) as error:
        struct_of(Search).build({"query": "python", "page": {"size": 500}})
    return error.value


def _indexed_error():
    with pytest.raises(SchemaTypeError) as error:
        struct_of(Search).build({"query": "python", "tags": [1, "no", 3]})
    return error.value


def _round_trip(error, how):
    return {
        "pickle": lambda e: pickle.loads(pickle.dumps(e)),
        "copy": copy.copy,
        "deepcopy": copy.deepcopy,
    }[how](error)


_HOWS = ["pickle", "copy", "deepcopy"]


# ------------------------------------------------------------ nested error


@pytest.mark.parametrize("how", _HOWS)
def test_nested_error_keeps_its_message(how):
    """README: `str(error) == "page: size: too large: 500, maximum 100"` — a round trip must not reword it."""
    revived = _round_trip(_nested_error(), how)

    assert str(revived) == "page: size: too large: 500, maximum 100"


@pytest.mark.parametrize("how", _HOWS)
def test_nested_error_keeps_its_path(how):
    """README, 'Guarantees': the errors 'carry `path` and `leaf`' — as data, so the data must survive transport."""
    revived = _round_trip(_nested_error(), how)

    assert revived.path == ("page", "size")


@pytest.mark.parametrize("how", _HOWS)
def test_nested_error_keeps_its_leaf(how):
    """README, 'Guarantees': `leaf` is the reason without the path."""
    revived = _round_trip(_nested_error(), how)

    assert revived.leaf == "too large: 500, maximum 100"


@pytest.mark.parametrize("how", _HOWS)
def test_nested_error_keeps_its_class(how):
    """README, 'Public API': a revived error is still the schema class, not a plain ValueError."""
    revived = _round_trip(_nested_error(), how)

    assert type(revived) is SchemaValueError
    assert isinstance(revived, ValueError)


# ----------------------------------------------------------- indexed error


@pytest.mark.parametrize("how", _HOWS)
def test_indexed_error_keeps_its_message(how):
    """README, 'Guarantees': 'Errors retain the complete field and list-index path'."""
    revived = _round_trip(_indexed_error(), how)

    assert str(revived) == "tags: [1]: expected int, got str"


@pytest.mark.parametrize("how", _HOWS)
def test_list_index_survives_as_an_int(how):
    """README, 'Guarantees': the path is data — an index must come back an int, not the text '[1]'."""
    revived = _round_trip(_indexed_error(), how)

    assert revived.path == ("tags", 1)
    assert type(revived.path[1]) is int


@pytest.mark.parametrize("how", _HOWS)
def test_indexed_error_keeps_its_class(how):
    """README, 'Public API': a wrong item type is a `SchemaTypeError` before and after transport."""
    revived = _round_trip(_indexed_error(), how)

    assert type(revived) is SchemaTypeError
    assert isinstance(revived, TypeError)


# --------------------------------------------------------- reduce mechanics


def test_reduce_rebuilds_from_leaf_and_path_not_from_the_rendered_line():
    """The rendered line is output, not input: reconstruction must use the arguments the constructor takes."""
    error = SchemaValueError("too large: 500, maximum 100", ("page", "size"))

    cls, args, _state = error.__reduce__()

    assert cls is SchemaValueError
    assert args == ("too large: 500, maximum 100", ("page", "size"))


@pytest.mark.parametrize("how", _HOWS)
def test_path_stays_a_tuple(how):
    """README, 'Guarantees': `path` is a tuple; a round trip must not hand back a list."""
    revived = _round_trip(_nested_error(), how)

    assert type(revived.path) is tuple


@pytest.mark.parametrize("how", _HOWS)
def test_args_are_unchanged(how):
    """`str()` reads from args; the round trip must leave them exactly as raised."""
    original = _nested_error()
    revived = _round_trip(original, how)

    assert revived.args == original.args
    assert revived.args == ("page: size: too large: 500, maximum 100",)


@pytest.mark.parametrize("how", _HOWS)
def test_added_notes_survive(how):
    """PEP 678 notes hang off the exception; reconstruction must not drop what a wrapper attached."""
    error = _nested_error()
    error.add_note("retry with a smaller page")

    revived = _round_trip(error, how)

    assert revived.__notes__ == ["retry with a smaller page"]


@pytest.mark.parametrize("how", _HOWS)
def test_wrapper_attributes_survive(how):
    """A wrapper may tag an error with its own context; reconstruction must not drop that either."""
    error = _nested_error()
    error.request_id = "abc-123"

    revived = _round_trip(error, how)

    assert revived.request_id == "abc-123"


@pytest.mark.parametrize("how", _HOWS)
def test_a_bare_leaf_error_round_trips(how):
    """README, 'Public API': the classes are exported for wrappers to raise, so a path-less error must travel too."""
    error = SchemaTypeError("expected int, got str")

    revived = _round_trip(error, how)

    assert str(revived) == "expected int, got str"
    assert revived.leaf == "expected int, got str"
    assert revived.path == ()


def test_pickle_survives_every_protocol():
    """A wrapper picks its own protocol; none of them may lose the structure."""
    error = _nested_error()

    for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
        revived = pickle.loads(pickle.dumps(error, protocol))

        assert revived.path == ("page", "size"), f"protocol {protocol}"
        assert revived.leaf == "too large: 500, maximum 100", f"protocol {protocol}"
        assert str(revived) == "page: size: too large: 500, maximum 100", f"protocol {protocol}"


def test_deepcopy_does_not_share_mutable_notes():
    """deepcopy means deep: a copied error's notes must not alias the original's."""
    error = _nested_error()
    error.add_note("first")

    revived = copy.deepcopy(error)
    revived.add_note("second")

    assert error.__notes__ == ["first"]
    assert revived.__notes__ == ["first", "second"]

# pytypehint

[![PyPI](https://img.shields.io/pypi/v/pytypehint.svg)](https://pypi.org/project/pytypehint/)

`pytypehint` compiles Python type hints into strict, inspectable schemas. A
hint carries everything there is to know about a field — its type, its limits,
and its presentation — so the dataclass is the single source of truth: the
core validates plain input data, fills fresh defaults and constructs dataclass
instances; wrapper authors read the same schema to render controls, coerce
external input and execute functions themselves. What the core hands them is
raw, inspectable structure, never an opinion about it: interpretive
conveniences belong to wrappers and to intermediate packages built on the core.
Stdlib only; Python 3.11+; `py.typed` included.

```bash
pip install pytypehint
```

```python
from dataclasses import dataclass, field
from typing import Annotated
from pytypehint import Label, Max, Min, signature_of, struct_of

@dataclass(frozen=True)
class Page:
    number: Annotated[int, Min(1)] = 1
    size: Annotated[int, Min(1), Max(100), Label("Page size")] = 20

@dataclass
class Search:
    query: str
    page: Page = Page()
    tags: list[str] = field(default_factory=list)

value = struct_of(Search).build({"query": "python", "page": {"size": 50}})
# Search(query='python', page=Page(number=1, size=50), tags=[])

try:
    struct_of(Search).build({"query": "python", "page": {"size": 500}})
except ValueError as error:
    assert str(error) == "page: size: too large: 500, maximum 100"

def search(query: str, page: Page = Page()): ...
kwargs = signature_of(search).build({"query": "python"})
search(**kwargs)  # execution belongs to the caller
```

## Guarantees

- Exact types: `type(value) is T`; the core never coerces.
- Data enters as dictionaries and lists; dataclass instances leave through `build`.
- Defaults are certified at compilation and rematerialized fresh per missing key.
- Invalid constraints fail while compiling the schema.
- Errors retain the complete field and list-index path, as the message text and
  as data: `SchemaTypeError` and `SchemaValueError` carry `path` and `leaf`, and
  subclass `TypeError` and `ValueError`.
- Notation atoms are stored and cross-checked but never affect validation;
  presentation belongs to the wrapper.
- `Struct`, `Field` and `Signature` compare by identity; compile once and share.
- `build` validates the input once and constructs directly; the cost is linear.
- `resolve` validates and fills defaults without constructing nested dictionaries.
- `Signature.build` returns constructed keyword arguments and never invokes the function.

## Vocabulary

| Hint | Shape | Input |
|---|---|---|
| `int` | `Int` | exact `int` |
| `float` | `Float` | exact `float` |
| `str` | `Str` | exact `str` |
| `bool` | `Bool` | exact `bool` |
| `date` | `Date` | exact `datetime.date` |
| `time` | `Time` | exact naive `datetime.time` |
| `Enum` subclass | `EnumShape` | exact member type |
| `None` | `NoneShape` | `None` |
| `list[X]` | `List` | list; nesting and union items supported |
| dataclass | `Struct` | dictionary; `build` constructs it |
| `A \| B` | tuple of shapes | exact scalar type or routed dataclass dictionary |
| `Literal[...]` | `Int` or `Str` with `Choices` | homogeneous `int` or `str` literals |

## Public API

Everything public is exported from `pytypehint`:

- `struct_of`, `signature_of`;
- `Struct`, `Field`, `Signature`;
- errors: `SchemaTypeError`, `SchemaValueError`;
- `Shape`, `Int`, `Float`, `Str`, `Bool`, `Date`, `Time`, `List`,
  `NoneShape`, `EnumShape`;
- limits: `Min`, `Max`, `Choices`, `MultipleOf`, `Pattern`, `IsPathFile`;
- notation: `Label`, `Description`, `Placeholder`, `Step`, `Slider`,
  `IsPassword`, `Rows`, `Extra`, `OptionalToggle`;
- `MISSING`.

`Extra(key, value)` takes a namespaced key (`"package.name"`) and any string
value; a shape merges every `Extra` on its hint into a read-only `extras`
dictionary that the core stores and never reads.

Start with [the design principles](docs/philosophy.md), then read
[build](docs/build.md), [resolve](docs/resolve.md), [defaults](docs/defaults.md),
[vocabulary](docs/vocabulary.md), [atoms](docs/atoms.md),
[restrictions](docs/restrictions.md), and [comparison](docs/comparison.md).
# pytypehint

[![PyPI](https://img.shields.io/pypi/v/pytypehint.svg)](https://pypi.org/project/pytypehint/)

`pytypehint` compiles standard Python type hints into strict, inspectable schemas.

Your code remains ordinary Python:

* **No custom models, decorators, mutation, registration, or runtime hooks.**
* **Your dataclasses remain untouched and work without `pytypehint`.**
* **The library only observes them from the outside and compiles a separate schema.**

The dataclass is the single source of truth:

* types come from type hints;
* constraints and presentation come from `Annotated`;
* defaults are validated and rematerialized fresh;
* plain input is validated and converted into dataclass instances.

Wrappers inspect the same schema to render controls, coerce external input, generate interfaces, or execute functions. The core never imposes those policies.

**Standard Python in. Raw, strict structure out.**

Stdlib only. Python 3.11+. `py.typed` included.

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
- A union routes by the exact runtime type of the value. Where two options share
  that type — `list[str] | list[int]`, `A | B` — the caller names one; the core
  never guesses from the contents, from the option order, or by trying them.
- Defaults are certified at compilation and rematerialized per missing key.
  Immutable scalar values and enum members may be reused; lists and dataclass
  instances are reconstructed. A `default_factory` runs during certification
  and again whenever its missing value is served.
- Invalid atom combinations and contradictions the core can determine exactly
  fail while compiling the schema. The core does not attempt a general
  satisfiability proof across unrelated constraints.
- Errors retain the complete field and list-index path, as the message text and
  as data: `SchemaTypeError` and `SchemaValueError` carry `path` and `leaf`, and
  subclass `TypeError` and `ValueError`.
- Notation atoms are stored and cross-checked but never affect validation;
  presentation belongs to the wrapper.
- `Struct`, `Field` and `Signature` compare by identity; compile once and share.
- `build` validates supplied input values once and then constructs directly.
  Missing defaults are materialized and validated at their own depth.
- `resolve` validates the supplied tree and fills defaults for missing fields at
  the level being resolved. A supplied nested dataclass dictionary remains a
  dictionary and is not recursively expanded with that dataclass's defaults;
  `build` fills those defaults while constructing the nested instance.
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
| `list[str] \| list[int]` | tuple of shapes | `{"$type": "list[str]", "$value": [...]}` |
| `Literal[...]` | `Int` or `Str` with `Choices` | homogeneous `int` or `str` literals |

Python allows `list[str | int]` and `list[str] | list[int]`, and they mean
different things. The core keeps both, and asks for a discriminator only where
the value cannot supply one:

```python
mixed: list[str | int]          # {"mixed": ["a", 1, "b", 2]}
either: list[str] | list[int]   # {"either": {"$type": "list[str]", "$value": ["a", "b"]}}
```

Every element of `mixed` routes by its own exact type. `either` chooses one
option for the whole list, and both options arrive as a `list`, so the caller
names the one it meant. See [build.md](docs/build.md).

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

`Extra(key, value)` takes a key containing a namespace separator
(`"package.name"`; a dot is required) and any string value, including an empty
string. A shape merges every `Extra` on its hint by key; the rightmost/outermost
value wins for a repeated key. Internally the pairs are sorted and immutable.
The `extras` property returns a fresh `dict[str, str]` on every access, so callers
may modify that snapshot without changing the shape. The core stores these
entries but never interprets them.

Start with [the design principles](docs/philosophy.md), then read
[build](docs/build.md), [resolve](docs/resolve.md), [defaults](docs/defaults.md),
[vocabulary](docs/vocabulary.md), [atoms](docs/atoms.md),
[restrictions](docs/restrictions.md), and [comparison](docs/comparison.md).

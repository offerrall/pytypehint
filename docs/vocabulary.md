# Vocabulary

Validation is exact: a hint `T` accepts only `type(value) is T`. There is no
coercion, subclass acceptance or `int`/`bool` leakage.

| Hint | Shape | Example |
|---|---|---|
| `int` | `Int` | `n: int` |
| `float` | `Float` | `ratio: float` |
| `str` | `Str` | `name: str` |
| `bool` | `Bool` | `active: bool` |
| `datetime.date` | `Date` | `day: date` |
| `datetime.time` | `Time` | `at: time` |
| Enum subclass | `EnumShape` | `role: Role` |
| `None` | `NoneShape` | normally part of `X | None` |
| `list[X]` | `List` | `tags: list[str]` |
| dataclass | `Struct` | `page: Page` |
| union | tuple of shapes | `value: int | str` |
| `Literal[...]` | `Int` or `Str` with `Choices` | `mode: Literal["fast", "safe"]` |

`float` does not accept `int`; `int` does not accept `bool`. `Time` requires a
naive `time`. Enum values must be members of the exact enum class. `None` alone
is rejected because it describes no useful field; use `X | None`.

Lists validate their length and every indexed item. Nesting and union-valued
items are supported:

```python
from dataclasses import dataclass

@dataclass
class Created:
    id: int

@dataclass
class Deleted:
    id: int

matrix: list[list[int]]
events: list[Created | Deleted]
holes: list[int | None]
```

`None` is a valid item option: `list[int | None]` accepts `None` holes as values.
A `None` item is data, not field optionality; `list[None]` alone remains
rejected. Every option of a union item must compile to a distinct type, because
an item routes by its exact runtime type — see
[restrictions.md](restrictions.md).

Dataclasses accept dictionaries as input. `build` recursively constructs the
instance; input instances are rejected. Two or more dataclass alternatives use
the `$type` discriminator described in [build.md](build.md).

Union options retain user order. Metadata for a specific option belongs inside
that option: `Annotated[int, Min(0)] | str`. Field atoms such as `Label` belong
on the outer field layer.

`Literal` is shorthand for exact choices. Its values must all have the same
type and may be only `int` or `str`; float choices use
`Annotated[float, Choices(values=(...))]`.

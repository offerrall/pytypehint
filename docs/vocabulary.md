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
| `None` | `NoneShape` | normally part of `X \| None` |
| `list[X]` | `List` | `tags: list[str]` |
| dataclass | `Struct` | `page: Page` |
| union | tuple of shapes | `value: int \| str` |
| ambiguous union | tuple of shapes | `value: list[str] \| list[int]` |
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
rejected.

## `list[str | int]` is not `list[str] | list[int]`

Python allows both, and they say different things. The core keeps them apart.

```python
mixed: list[str | int]        # one list whose items may be either
either: list[str] | list[int] # one list of str, or one list of int
```

`mixed` routes every element by its own exact type, so it takes its value
directly:

```python
{"mixed": ["a", 1, "b", 2]}
```

`either` chooses once, for the whole list. Both options arrive as a `list`, so
the value cannot say which one it is and the caller says it:

```python
{"either": {"$type": "list[str]", "$value": ["a", "b"]}}
{"either": {"$type": "list[int]", "$value": [1, 2]}}
```

`["a", 1]` is valid for `mixed` and invalid for `either` under either option.
The discriminator is required only where the runtime type is shared — see
[build.md](build.md) for the wrapper and [restrictions.md](restrictions.md) for
the identities it names.

Dataclasses accept dictionaries as input. `build` recursively constructs the
instance; input instances are rejected. Two or more dataclass alternatives use
the inline `$type` discriminator described in [build.md](build.md), including as
list items: `list[Shirt | Mug]` discriminates each element, while
`list[Shirt] | list[Mug]` wraps the whole list.

Union options retain user order. Metadata for a specific option belongs inside
that option: `Annotated[int, Min(0)] | str`. Field atoms such as `Label` belong
on the outer field layer.

`Literal` is shorthand for exact choices. Its values must all have the same
type and may be only `int` or `str`; float choices use
`Annotated[float, Choices(values=(...))]`.

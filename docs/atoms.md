# Atoms

Use frozen atoms inside `Annotated`. Limits validate values; notation is stored
for consumers and does not change runtime validation.

```python
from typing import Annotated
from pytypehint import Label, Max, Min

Quantity = Annotated[int, Min(1), Max(100), Label("Quantity")]
```

| Shape | Accepted atoms |
|---|---|
| `Int` | `Min`, `Max`, `Choices`, `MultipleOf`, `Step`, `Slider`, `Placeholder`, `Extra` |
| `Float` | `Min`, `Max`, `Choices`, `Step`, `Slider`, `Placeholder`, `Extra` |
| `Str` | `Min`, `Max`, `Choices`, `Pattern`, `FileHint`, `IsPassword`, `Rows`, `Placeholder`, `Extra` |
| `Date`, `Time` | `Min`, `Max`, `Choices`, `Placeholder`, `Extra` |
| `List`, `Tuple` | `Min`, `Max`, `Extra` |
| `Bool`, `NoneShape`, `EnumShape` | `Extra` |
| Nested dataclass (`Struct`) | No shape atoms |
| Any field | `Label`, `Description` |
| Field allowing `None` | `OptionalToggle` |

| Atom | Rule |
|---|---|
| `Min(value, exclusive=False)`, `Max(...)` | Bounds; strings and sequences use nonnegative integer lengths, inclusive only |
| `Choices(values=(...))` | Nonempty tuple of unique, hashable, exact-type values satisfying all other limits |
| `MultipleOf(value)` | Positive integer divisor; `Int` only |
| `Pattern(regex, message=None)` | Python `re.fullmatch`; optional custom mismatch message |
| `Step(value)` | Positive finite numeric notation |
| `Slider(show_value=True)` | Numeric notation; requires both bounds |
| `Label(text)`, `Description(text)` | Nonempty field text |
| `Placeholder(text)` | Nonempty scalar input notation |
| `IsPassword()`, `Rows(n)` | String notation; rows must be positive |
| `OptionalToggle(enabled)` | Boolean field notation; absent leaves the consumer's choice |
| `Extra(key, value)` | Namespaced key containing a dot; string value, including empty |

`exclusive` and `message` are keyword-only. Numeric atoms must match their shape's
rules; `Float` allows finite integer bounds, but choices remain exact floats.
Compilation rejects unsupported atoms and contradictions it can determine:
empty ranges, impossible integer multiples, invalid choices, missing slider
bounds and `OptionalToggle` without a `None` option. It does not prove general
satisfiability of combined regex and length constraints.

## File names

`FileHint(extensions=(), min_size=None, max_size=None)` marks a string as a file
name. Extensions must be unique lowercase dotted suffixes. Sizes are nonnegative
integer byte counts, with `min_size <= max_size` when both are present.

The core checks suffixes case-insensitively, after string lengths and pattern and
before choices. Empty extensions accept any suffix. Defaults and choices receive
the same check. File existence, file kind and sizes are checked by the consumer;
pytypehint never reads the filesystem or changes the string into a path object.

## Layering and extras

For repeated atom classes, the outer/rightmost atom wins:

```python
Percent = Annotated[int, Min(0), Max(100)]
Narrow = Annotated[Percent, Max(50)]
```

`Extra` merges per key. Shapes store sorted unique pairs and return a fresh
`extras` dictionary on each access; modifying it does not change the shape.
Manually supplied `_extras` must be a tuple of unique string pairs.

Put type atoms inside individual union options. Field atoms from different
options must agree unless an outer field atom overrides them. Field atoms are
not allowed on list items or tuple positions.

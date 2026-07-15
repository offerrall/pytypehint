# Atoms

Atoms are frozen values inside `Annotated`. Limits affect validation; notation
is stored for wrappers and ignored by validation.

| Shape | Accepted atoms |
|---|---|
| `Int` | `Min`, `Max`, `Choices`, `MultipleOf`, `Step`, `Slider`, `Placeholder`, `Extra` |
| `Float` | `Min`, `Max`, `Choices`, `Step`, `Slider`, `Placeholder`, `Extra` |
| `Str` | `Min`, `Max`, `Choices`, `Pattern`, `IsPathFile`, `IsPassword`, `Rows`, `Placeholder`, `Extra` |
| `Date`, `Time` | `Min`, `Max`, `Choices`, `Placeholder`, `Extra` |
| `List` | `Min`, `Max` for length, `Extra` |
| `Bool`, `NoneShape` | `Extra` |
| `EnumShape`, dataclass (`Struct`) | none; annotate struct fields, not nesting |
| any field | `Label`, `Description` |
| optional field (`X \| None`) | `OptionalToggle` |

## Atoms

`Min(value, *, exclusive=False)` and `Max(...)` set lower and upper bounds.
On strings and lists they constrain length and cannot be exclusive.

`Choices(values=(...))` requires a non-empty tuple of unique, hashable values.
Choices must have the shape's exact type and satisfy its other limits.

`MultipleOf(value)` accepts a positive integer and applies only to `Int`.
Integer-only divisibility avoids floating-point ambiguity.

`Pattern(regex, *, message=None)` applies a full regular-expression match to
`Str`. A custom message replaces the standard mismatch message.

`Step(value)` is positive numeric wrapper notation. `Slider(show_value=True)`
is notation for numeric fields and requires both `Min` and `Max`.

`Placeholder(text)` is non-empty wrapper notation for scalar inputs.
`IsPassword()` and `Rows(n)` are string notation; rows must be positive.

`Extra(text)` is opaque, non-empty wrapper notation. The core stores it and
never interprets it; layering follows the standard rule.

`IsPathFile(extensions=(...))` marks a string as a path input. Extensions are
lowercase dotted suffixes; validation checks the suffix, never file existence.

`Label(text)` and `Description(text)` are non-empty field-level notation.

`OptionalToggle(enabled)` is field-level notation for `X | None`. `True` starts
a wrapper toggle on, `False` starts it off, and absence leaves the choice to the
wrapper. It never changes resolution or defaults.

## Compile-time cross-checks

The schema rejects empty ranges; choices outside bounds or failing pattern,
multiple or extension rules; ranges containing no valid multiple; sliders
without both bounds; wrong bound types; and `OptionalToggle` on a non-optional
field. These contradictions fail during schema compilation because a compiled
schema must be structurally valid. Compilation rejects contradictions it can
determine exactly; it does not attempt a general satisfiability proof across
constraints such as a regular expression combined with length bounds.

Unsupported metadata reports `unsupported metadata for <type>: <atom>`.
Metadata across a multi-type union must be placed per option.

## Layering

For repeated atom classes, the outer layer wins; within one layer, the
rightmost atom wins. The rule applies uniformly to limits and field notation:

```python
from typing import Annotated
from pytypehint import Max, Min, OptionalToggle

Percent = Annotated[int, Min(0), Max(100)]
Narrow = Annotated[Percent, Max(50)]

Optional = Annotated[int | None, OptionalToggle(True)]
Closed = Annotated[Optional, OptionalToggle(False)]
```

Conflicting field atoms hoisted from different union options fail with
`conflicting ... across union options`; an explicit outer atom overrides them.

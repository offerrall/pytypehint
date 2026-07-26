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
| `EnumShape` | `Extra` |
| dataclass (`Struct`) | none; annotate struct fields, not nesting |
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

`Extra(key, value)` carries wrapper notation the vocabulary does not name. The
key is namespaced — `"package.name"`, the dot required — so that two packages
annotating one field cannot collide by accident and every entry names its owner.
The value is any string, empty included: the core stores it and never reads it,
so what an empty value means is the wrapper's business.

Several `Extra` atoms on one hint merge by key. The shape stores them as a
sorted tuple of pairs, which keeps it hashable and its equality independent of
the order the atoms were written in, and exposes them as a read-only `extras`
dict built on access. Filtering by namespace is the wrapper's job:
`{k: v for k, v in shape.extras.items() if k.startswith("ledform.")}`.

`IsPathFile(extensions=(), min_size=None, max_size=None)` marks a `str` as a path
to an existing file. Extensions are lowercase dotted suffixes; sizes are byte
counts, each `int` or `None`, never negative, and `min_size` may not exceed
`max_size` (`bool` is not an `int` here). Validation checks the extension, that
the path exists, that it is a regular file and not a directory, and the size.

The value is and remains exactly `str`: `pathlib.Path` is used only inside the
validation, to inspect the file. Nothing is coerced, normalized, resolved or made
absolute.

```python
from typing import Annotated
from pytypehint import IsPathFile

FilePath = Annotated[
    str,
    IsPathFile(
        extensions=(".pdf",),
        max_size=10 * 1024 * 1024,
    ),
]
```

The guarantee is about the moment of validation: the file existed and met the
contract when it was validated. Nothing promises it still does afterwards.
Relative paths are accepted and interpreted against the current working
directory, exactly as Python does; the value stays as written. A symlink is
followed: a live link to a regular file is accepted, and a broken one fails as
non-existent. Defaults and `Choices` are certified with these same guarantees
when the schema compiles.

`Label(text)` and `Description(text)` are non-empty field-level notation.

`OptionalToggle(enabled)` is field-level notation for `X | None`. `True` starts
a wrapper toggle on, `False` starts it off, and absence leaves the choice to the
wrapper. It never changes resolution or defaults.

## Compile-time cross-checks

The schema rejects empty ranges; choices outside bounds or failing pattern,
multiple or file rules; ranges containing no valid multiple; sliders
without both bounds; wrong bound types; and `OptionalToggle` on a non-optional
field. A choice under `IsPathFile` must satisfy the whole file contract, not only
its suffix, and so must a certified default. These contradictions fail during
schema compilation because a compiled
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

Extras layer per key rather than per `Extra` class: different keys accumulate on
the shape, and a repeated key follows the rule above. Outer and rightmost are
one mechanism here — typing flattens `Annotated` before compilation, so the
outer layer *is* the rightmost atom:

```python
from typing import Annotated
from pytypehint import Extra

Themed = Annotated[int, Extra("ledform.color", "red"), Extra("ledform.rows", "2")]
Blue = Annotated[Themed, Extra("ledform.color", "blue")]
# extras == {"ledform.color": "blue", "ledform.rows": "2"}
```

Conflicting field atoms hoisted from different union options fail with
`conflicting ... across union options`; an explicit outer atom overrides them.

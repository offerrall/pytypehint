# Atoms

Atoms are frozen values inside `Annotated`. Limits affect validation; notation
is stored for wrappers and ignored by validation.

| Shape | Accepted atoms |
|---|---|
| `Int` | `Min`, `Max`, `Choices`, `MultipleOf`, `Step`, `Slider`, `Placeholder`, `Extra` |
| `Float` | `Min`, `Max`, `Choices`, `Step`, `Slider`, `Placeholder`, `Extra` |
| `Str` | `Min`, `Max`, `Choices`, `Pattern`, `FileHint`, `IsPassword`, `Rows`, `Placeholder`, `Extra` |
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
the order the atoms were written in, and exposes them as an `extras` dict rebuilt
on each access. That dict is a detached snapshot rather than a view: writing to
it, inserting into it or clearing it is allowed and never reaches the shape.
Filtering by namespace is the wrapper's job:
`{k: v for k, v in shape.extras.items() if k.startswith("ledform.")}`.

`FileHint(extensions=(), min_size=None, max_size=None)` marks a `str` whose text
names a file, and carries that file's contract: the suffixes the name may take and
the byte sizes the file must fall between. Extensions are lowercase dotted
suffixes and may not repeat; sizes are byte counts, each `int` or `None`, never
negative, and `min_size` may not exceed `max_size` (`bool` is not an `int` here).
Validation checks the extension against the text of the value, and stops there.

The value is and remains exactly `str`. Nothing is coerced to `pathlib.Path`,
normalized, resolved, expanded or made absolute, so the string that arrives is the
string that validates and the string that is served.

```python
from typing import Annotated
from pytypehint import FileHint

FilePath = Annotated[
    str,
    FileHint(
        extensions=(".pdf",),
        max_size=10 * 1024 * 1024,
    ),
]
```

Every validation the core performs is answered by the schema and the value between
them, and this atom is where that line is easiest to see. An extension is text:
`"report.pdf"` ends in `.pdf` or it does not, and the answer is the same in every
process, on every machine, with or without a disk attached — so the core answers
it. Existence and size are the world: they need a filesystem, a working directory
and a moment in time before they mean anything at all. Those two are therefore
stated rather than checked. They travel in the document as contract, for the
wrapper to apply where it has the file in hand — at the upload, at the
command-line argument, at the request that actually opens the bytes.

The division is the general rule applied to one atom, and
[philosophy.md](philosophy.md) sets out why it is a gain rather than a
renunciation: a fact about the world is only true where and when it is read, and a
validator that reads outside the process takes the determinism of
[the document](contract.md) with it. The core describes the file; the wrapper
verifies it.

`Label(text)` and `Description(text)` are non-empty field-level notation.

`OptionalToggle(enabled)` is field-level notation for `X | None`. `True` starts
a wrapper toggle on, `False` starts it off, and absence leaves the choice to the
wrapper. It never changes resolution or defaults.

## Compile-time cross-checks

The schema rejects empty ranges; choices outside bounds or failing pattern,
multiple or file rules; ranges containing no valid multiple; sliders
without both bounds; wrong bound types; and `OptionalToggle` on a non-optional
field. A choice under `FileHint` must carry an accepted extension, and so must a
certified default — that is the whole of the contract the core can settle here.
These contradictions fail during schema compilation because a compiled
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

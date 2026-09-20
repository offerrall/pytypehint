# Immutable models

`@immutable` creates a frozen, slotted, keyword-only dataclass. It validates each
completed construction using the existing pytypehint constraints and errors.
`dataclasses.replace` constructs and validates a new instance normally.

```python
from dataclasses import replace
from typing import Annotated
from pytypehint import Min, immutable

@immutable
class Size:
    width: Annotated[int, Min(1)]
    height: Annotated[int, Min(1)]

original = Size(width=1920, height=1080)
smaller = replace(original, width=960, height=540)
```

## Allowed fields

| Type | Contract |
|---|---|
| `int`, `float`, `bool`, `str`, `date`, `time` | Exact types and normal pytypehint constraints |
| `Literal`, unions, optional fields | Every option must satisfy this table |
| Fixed, variadic or empty tuples | Every position must satisfy this table |
| Another `@immutable` model | Exact type; construction must have completed successfully |

Lists and other mutable containers are rejected even inside tuples or unused union
branches. Ordinary dataclasses, including frozen ones, are rejected. Enums are
excluded because their members can carry mutable data. Use literals when suitable.

Definitions compile lazily before the first initialization, so module-level forward
references and recursive model definitions can resolve. All reachable model field
types are checked. Local forward references need resolvable namespaces, as with
`get_type_hints`. Schemas are cached; keep model definitions unchanged after use.

## Reusing values

Scalars and new tuples are checked on construction. An already validated child
model keeps its identity and is accepted without inspecting its fields again.
A tuple of children still requires checking its length and each child's exact type.
A new parent therefore pays for its own fields and tuple contents, not every
field below its existing child models.

Successful construction is recorded by identity using weak references: this adds
per-instance bookkeeping without retaining the instances. An unfinished or failed
instance cannot be reused as a validated child. Recursive type definitions work;
self-referential object cycles cannot be constructed through this API.

Default values and factories follow Python's constructor semantics. Factories run
only when their field is omitted, once per construction. The decorator does not
execute factories to certify a schema; it checks the actual resulting values.
An overridden invalid value default is not used or validated by that construction.
`struct_of` retains its separate [default certification](defaults.md) behavior.

## Python behavior

- Decorate every subclass. Bases must also use `@immutable`; fields are inherited.
- Constructor arguments and signatures remain those of the generated dataclass.
  `field()` is supported, subject to the existing restriction against `init=False`.
- `__post_init__` runs before final validation. Its exceptions propagate. The
  decorator guarantees the returned fields, not the inputs seen by that hook.
- `copy.copy` and `copy.deepcopy` return the same immutable instance. Pickle
  reconstructs through the validated constructor, including `__post_init__`.
- Reinitializing an existing instance is rejected.
- The generated `__setstate__` mutator is removed; pickle uses the constructor.
- Custom `__init__`, `__new__`, attribute-read overrides and copy/pickle hooks are
  unsupported. `InitVar` is unsupported. Do not combine `@immutable` and `@dataclass`.

The guarantee covers declared instance fields through normal Python use.
Deliberate mutation with `object.__setattr__`, changing class definitions or
modifying library internals bypasses it. Methods and hooks remain user code;
validation cannot undo their external effects. Use ordinary dataclasses and
`struct_of` when the stricter immutable contract does not fit.

Model classes and compiled contracts remain registered for the process lifetime;
define reusable models rather than generating a new class for each value.

`resolve`, `build`, `decode` and `to_dict` remain available through `struct_of`.
Their input rules and full recursive validation are unchanged; the reuse shortcut
belongs only to `@immutable` construction.

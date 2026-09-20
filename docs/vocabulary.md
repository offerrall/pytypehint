# Types and API

Validation requires exact types: `float` rejects `int`, `int` rejects `bool`,
and subclasses are rejected. [Decode](decode.md) restores portable representations
before validation when needed.

| Hint | Compiled shape |
|---|---|
| `int`, `float`, `str`, `bool` | `Int`, `Float`, `Str`, `Bool` |
| `datetime.date`, `datetime.time` | `Date`, `Time` |
| Enum subclass | `EnumShape` |
| `None` in a union | `NoneShape` |
| `list[X]` | `List` |
| `tuple[X, Y]`, `tuple[X, ...]`, `tuple[()]` | `Tuple` |
| Dataclass | `Struct` |
| Union | Ordered tuple of shapes |
| `Literal[...]` | `Int` or `Str` with `Choices` |

Floats must be finite; times must be naive with whole-second precision. Enums
require exact members. `Literal` values must be uniformly `int` or `str`.
Use `Annotated[float, Choices(values=(0.5, 1.0))]` for float choices.

Lists, tuples and dataclasses support nesting, recursion and unions. Dataclass
input uses dictionaries; `build` constructs instances. Bare `None`, `list[None]`
and tuple slots containing only `None` are rejected; `list[int | None]` is valid.

```python
mixed: list[str | int]         # accepts ["a", 1]
either: list[str] | list[int]  # needs {"$type": "list[str]", "$value": ["a"]}
```

Union options retain declaration order. Put type constraints on the option:
`Annotated[int, Min(0)] | str`. Field notation such as `Label` belongs on the
outer field. See [atoms](atoms.md), [tuples](tuples.md) and
[restrictions](restrictions.md).

There is no `datetime` or path shape. Represent timestamp policy with a dataclass;
use a `str` annotated with `FileHint` for file names.

## Public API

Everything public is exported from `pytypehint`:

- `struct_of`, `signature_of`, `immutable`;
- `Struct`, `Field`, `Signature`;
- `SchemaTypeError`, `SchemaValueError`;
- `Shape`, `Int`, `Float`, `Str`, `Bool`, `Date`, `Time`, `List`, `Tuple`,
  `NoneShape`, `EnumShape`;
- `Min`, `Max`, `Choices`, `MultipleOf`, `Pattern`, `FileHint`;
- `Label`, `Description`, `Placeholder`, `Step`, `Slider`, `IsPassword`, `Rows`,
  `Extra`, `OptionalToggle`;
- `MISSING`.

`Struct` and `Signature` expose `.build(data)`, `.resolve(data)`, `.decode(data)`
and `.to_dict()`. `Struct.fields` and `Signature.params` contain `Field` objects;
`Field.shape` contains the available shapes, and `Field.default` is `MISSING`
when no default exists. `Shape.option_id()` gives the discriminator identity.
`Struct`, `Field` and `Signature` compare by identity; compile once and reuse.

`@immutable` creates deeply immutable, automatically validated dataclasses with a
restricted field vocabulary. See [Immutable models](immutable.md).

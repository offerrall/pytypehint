# Encode

`schema.encode(value)` writes a valid value as the portable tree that
[decode](decode.md) reads. It is the inverse of `decode`:

```python
from dataclasses import dataclass
from datetime import date
from pytypehint import struct_of

@dataclass
class Booking:
    day: date
    guests: int | float = 2

schema = struct_of(Booking)
booking = Booking(day=date(2026, 8, 8))
written = schema.encode(booking)

assert written == {"day": "2026-08-08", "guests": {"$type": "int", "$value": 2}}
assert schema.build(schema.decode(written)) == booking
```

`Struct.encode` takes an exact instance of its dataclass. `Signature.encode`
takes a dictionary of arguments, such as the one `build` returns, and writes the
keys it is given; it fills no defaults and rejects unknown keys.

The result is a new tree of plain dictionaries, lists, strings, numbers, booleans
and `None`. The caller serializes it, for example with `json.dumps`. The value is
never modified, and the tree shares no container with it.

| Shape | Written as |
|---|---|
| `Date` | `"YYYY-MM-DD"` |
| `Time` | `"HH:MM:SS"` |
| `EnumShape` | Member name |
| `List`, `Tuple` | Array |
| `Struct` | Object of its fields |
| Others | The value itself |

## Unions

An option is named exactly where its portable spelling collides with another
option of the same slot, following the [portable contract](contract.md#values-and-defaults):
dataclass variants carry an inline `$type`, other colliding options use the
`$type`/`$value` wrapper, and unambiguous options are written bare. These are the
spellings `to_dict()` uses for defaults.

Options sharing a Python type, such as `Annotated[list[str], Min(1)] | list[int]`,
are told apart by the first option that accepts the value.

## Round trip

For a value that passes validation:

```python
schema.build(schema.decode(schema.encode(value))) == value
```

The same holds after `json.loads(json.dumps(...))`. Types are preserved: floats
stay floats, tuples stay tuples and each union value returns to its own option.

## Validation

Encode writes; it does not validate. It checks only what it needs in order to
write: the root type, that each value belongs to an option of its slot, and
fixed tuple lengths. Those failures raise `SchemaTypeError` or `SchemaValueError`
with the field names and indexes of the value in `path`.

A value outside its limits, such as a number below `Min`, is written faithfully,
and `build` rejects it when the tree is read back. Time fractions and offsets are
kept in the text for the same reason. Non-finite floats are written as they are
and have no standard JSON spelling. Cycles and excessive nesting can raise
`RecursionError`.

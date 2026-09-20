# Decode

`schema.decode(data)` restores portable representations before validation:

```python
from dataclasses import dataclass
from datetime import date
from pytypehint import struct_of

@dataclass
class Booking:
    day: date

schema = struct_of(Booking)
booking = schema.build(schema.decode({"day": "2026-08-08"}))
assert booking.day == date(2026, 8, 8)
```

The caller parses JSON text. Decode accepts the resulting plain dictionaries,
lists, strings, numbers, booleans and `None`; it does not parse or emit JSON.

| Shape | Restoration |
|---|---|
| `Date` | `"YYYY-MM-DD"` to `date` |
| `Time` | `"HH:MM"` or `"HH:MM:SS"`, optionally with fraction/offset, to `time` |
| `EnumShape` | Member name to member; aliases accepted |
| `Float` | Integer to float only when the value is exactly representable |
| `Tuple` | Array to tuple, decoding by position or repeated item slot |

Date and time spellings use ASCII digits. Time fractions accept 1–6 digits. Nonzero fractions and timezone offsets survive
restoration so validation can reject their precision or timezone. Compact dates,
week dates and compact times are not restored. Invalid spellings remain unchanged.
Enums use names, never member values.

Decode never converts numeric strings, boolean strings, empty strings to `None`,
tuples to lists or subclasses to base types. Actual Python tuples pass through
unchanged, including their contents. Wrong array lengths retain every item for
validation to report.

## Unions

Restoration occurs only when the portable value selects exactly one option.
Shared spellings require a named option:

| Union | Bare value | Named option |
|---|---|---|
| `int \| float` | `3` stays `int` | `{"$type": "float", "$value": 3}` |
| `str \| date` | Text stays `str` | `{"$type": "date", "$value": "2026-08-08"}` |
| `date \| time` | Text stays `str`, then fails validation | `{"$type": "time", "$value": "14:30"}` |
| Two enums | Text stays `str`, then fails validation | Enum class name and member name |
| `list[int] \| tuple[int, ...]` | Array stays `list` | `{"$type": "tuple[int, ...]", "$value": [3]}` |
| Multiple list or tuple variants | Array remains ambiguous | Option identity and array payload |

A wrapper contains exactly `$type` and `$value` and is accepted only for ambiguous
spellings. Decode consumes it when the restored runtime type identifies the
option. For multiple list or tuple variants, it retains the wrapper and decodes
its payload; [build](build.md) consumes it later.

Malformed wrappers, unknown identities and failed restorations remain undecoded.
A failed named date cannot silently become the `str` beside it. Dataclass unions
use inline `$type`; decode keeps that discriminator and descends into the selected
fields. Missing or invalid discriminators leave the dictionary undecoded.

## Preservation

Decode fills no defaults, runs no recipes, drops no unknown keys and raises no
schema validation errors. `resolve` or `build` reports invalid data afterward.
A non-dictionary root passes through unchanged.

Input is never mutated. Exact dictionaries and lists traversed by decode are
rebuilt recursively; aliases are not preserved. Other objects, including tuples
and dictionary/list subclasses such as `OrderedDict`, are returned unchanged.
Use plain containers for portable data. Cycles and excessive nesting can raise
`RecursionError`.

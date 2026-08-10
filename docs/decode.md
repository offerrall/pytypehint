# Decode

`Struct.decode(data)` and `Signature.decode(kwargs)` take a portable tree and
return an exact Python one. They prepare; they do not validate.

```python
from dataclasses import dataclass
from datetime import date
from pytypehint import struct_of

@dataclass
class User:
    name: str
    birthday: date

schema = struct_of(User)
wire = {"name": "Ana", "birthday": "2000-05-17"}

prepared = schema.decode(wire)
# {'name': 'Ana', 'birthday': datetime.date(2000, 5, 17)}

schema.build(prepared)      # User(name='Ana', birthday=date(2000, 5, 17))
schema.build(wire)          # birthday: expected date, got str
```

The four operations are separate on purpose, and each does one thing:

| Operation | In | Out |
|---|---|---|
| `.to_dict()` | — | the contract as a portable tree |
| `.decode(data)` | portable tree | exact Python tree |
| `.resolve(data)` | exact Python tree | validated tree, defaults filled |
| `.build(data)` | exact Python tree | constructed instance / kwargs |

## The portable tree

A portable tree is built from the types a JSON document can carry:

```text
dict   list   str   int   float   bool   None
```

The core does not read or write JSON text. `json.loads` and `json.dumps` belong
to the caller, and so does anything that is not JSON at all — a form post, a
message queue, a config file, another language's serializer:

```text
JSON text ──json.loads()──▶ portable tree ──decode()──▶ exact Python tree ──build()──▶ objects
```

Three of the core's types have no carrier in that tree and arrive spelled as
something else, and one more can lose part of itself on the way out:

| Shape | Portable spelling |
|---|---|
| `Date` | `"YYYY-MM-DD"` |
| `Time` | `"HH:MM"` or `"HH:MM:SS"` |
| `EnumShape` | the member's name, `"ADMIN"` |
| `Float` | a number; a whole float may arrive as `3` rather than `3.0` |

`decode` restores those four and does nothing else. Every other value passes
through unchanged.

## `decode` is not coercion

This is the line the operation exists to draw. Decode recovers a representation
the transport lost. Coercion reinterprets a value the author wrote, and it stays
outside the core, in the wrapper that knows what it is reading — a form, a
command line, an environment variable, an importer.

None of these happen, at any depth, under any schema:

```text
"3"      ──▶ int          "true"  ──▶ bool
"3.5"    ──▶ float        "false" ──▶ bool
""       ──▶ None         "null"  ──▶ None
tuple    ──▶ list         subclass ──▶ base type
```

A `str` field holding `"2026-08-08"` stays a `str`, however much it looks like a
date. The shape decides the reading; the text never does:

```python
@dataclass
class Post:
    slug: str

struct_of(Post).decode({"slug": "2026-08-08"})   # {'slug': '2026-08-08'}
```

And a value decode cannot restore is handed back exactly as it came, so that
validation reports it with its own coordinates and wording:

```python
@dataclass
class Booking:
    day: date

schema = struct_of(Booking)
schema.decode({"day": "2026-08-08"})   # {'day': date(2026, 8, 8)}
schema.decode({"day": "hello"})        # {'day': 'hello'}
schema.build({"day": "hello"})         # day: expected date, got str
```

Decode never raises a schema error. It has no opinion about whether a value is
acceptable — that is `resolve` and `build`, which already report it with a path
and a leaf. One failure, reported once, in one place.

## Canonical spellings

`date.fromisoformat` and `time.fromisoformat` accept far more than a canonical
form, and the two grammars overlap: `"20200101"` reads as a date *and* as a time,
and `"2020"` reads as `20:20`. Letting them decide would let the text of a value
select an option. So the accepted spellings are fixed, and they are disjoint —
one carries `-` and no `:`, the other the reverse:

| Shape | Accepted | Rejected, left as `str` |
|---|---|---|
| `Date` | `2026-08-08` | `20260808`, `2026-W32-6`, `2026-08-08T10:00`, `2026/08/08` |
| `Time` | `14:30`, `14:30:00`, `14:30:00.0` | `2020`, `1430`, `143000` |

A spelling the schema will refuse is still read, so the shape reports its own
rule rather than having the value fall through as "not a time at all":

```text
{"at": "10:00:00.5"}      ──▶ time(10, 0, 0, 500000)
                              at: time precision is limited to whole seconds
{"at": "10:00:00+02:00"}  ──▶ time(10, 0, tzinfo=…)
                              at: must be naive (no tzinfo): 10:00:00+02:00
```

A fraction of nothing but zeros — `"14:30:00.0"` through `"14:30:00.000000"` — is
read the same way and then leaves no rule to report: `Time` refuses a nonzero
`microsecond`, and there is none. Those spellings pass end to end, which is why
the accepted column carries one; a seventh digit is not an ISO time at all and
stays a `str`.

A canonical spelling that names no real day — `"2026-02-31"` — is left as `str`;
there is no date to produce, and validation names that better than decode could.

## Enums travel by member name

```python
class Status(Enum):
    ACTIVE = "active"
    CLOSED = "closed"

# {"status": "ACTIVE"}  ──▶  Status.ACTIVE
```

The name, not the value. A name is always a string, always identifies exactly one
member, and is what `to_dict` publishes; a value may be a tuple, an object, or
anything else a portable tree cannot carry. The two readings are genuinely
different, and picking the wrong one is silent:

```python
class Cross(Enum):
    RED = "BLUE"
    BLUE = "RED"

# "RED" is Cross.RED by name, and Cross.BLUE by value.
```

Decode returns the member itself, not a copy, so `is` comparisons hold. An alias
resolves to the member it aliases, because that is what the enum itself does;
`to_dict` publishes the canonical names only.

## Unions

The rule is one sentence, and it is the same one the rest of the core follows:

> The schema decides the reading. Where more than one option could read a
> portable value, the caller names the option, or the value stands as it came.

A value is decoded into an option when exactly one option can be spelled that
way. `float` alone reads `3` as `3.0`; `date` alone reads `"2026-08-08"` as a
date. Where the spellings collide, nothing is decoded:

| Field | Colliding spelling | Bare value decodes to |
|---|---|---|
| `int \| float` | a whole number | unchanged; `build` routes it to `int` |
| `str \| date` | text | unchanged; `build` routes it to `str` |
| `date \| time` | text | unchanged; `build` reports `expected date \| time, got str` |
| `Role \| Status` | text | unchanged; `build` reports the same |
| `list[str] \| list[int]` | an array | unchanged; `build` reports `ambiguous list` |

The caller names the option with the same two reserved keys and the same option
identities [build.md](build.md) already uses — but not with the same wrapper.
There are two, and they are worth keeping apart:

* **the validation wrapper**, which `build` and `resolve` read. It covers options
  that share a *Python runtime type*, and it is the one build.md documents;
* **the portable wrapper**, which only `decode` reads. It covers options that
  share a *portable spelling*, and `build` does not know it: given
  `{"$type": "date", "$value": "2026-08-08"}` on a `str | date` field, `build`
  alone reports `expected str | date, got dict`. It never sees one, because
  decode consumes it first.

The second set contains the first. Spelling and grammar are identical; what
differs is which operation reads it, and that is decided by the options, never by
the value:

```python
{"when": {"$type": "date", "$value": "2026-08-08"}}   # str | date
{"limit": {"$type": "float", "$value": 3}}            # int | float
{"at": {"$type": "time", "$value": "14:30:00"}}       # date | time
```

So:

* a **validation wrapper** — options that also share a Python runtime type, as in
  `list[str] | list[int]` — cannot be told apart after decoding either, so it is
  kept and only its payload is decoded;
* a **portable wrapper** — options that share only a spelling, as in `str | date`,
  `int | float`, `date | time`, `Role | Status` — names options that are distinct
  Python values once decoded, so it has done its work and is consumed.

Which one a slot takes is readable from the schema: options sharing a Python type
are always two or more `list`s, because any other pair sharing a type would have
been rejected as duplicate options.

```python
@dataclass
class Query:
    terms: list[str] | list[int]
    when: str | date

schema = struct_of(Query)
schema.decode({"terms": {"$type": "list[str]", "$value": ["a"]},
               "when":  {"$type": "date", "$value": "2026-08-08"}})
# {'terms': {'$type': 'list[str]', '$value': ['a']},   ← kept, build unwraps it
#  'when': datetime.date(2026, 8, 8)}                  ← consumed
```

A wrapper is accepted only where the reading is genuinely ambiguous, on the same
principle as the validation one. On a single-option field it is an ordinary
foreign dictionary and is left alone, so `build` reports it.

A wrapper whose payload did not reach the option it named is also left alone.
Consuming it would file the value under a different option in silence — a date
that failed to parse would settle as the `str` beside it:

```python
schema.decode({"when": {"$type": "date", "$value": "nonsense"}})
# {'when': {'$type': 'date', '$value': 'nonsense'}}
# build ──▶ when: expected str | date, got dict
```

Malformed wrappers — a missing `$type`, a non-string one, an unknown identity, a
missing `$value`, an extra key, a wrapper nested in a wrapper — are all handed
back untouched, and `build` reports each with the message and the coordinates it
already had. Decode never reproduces that diagnosis.

## Dataclasses

A dataclass arrives as a dict and decode descends into it by field name. Where a
union holds two or more dataclasses, it descends through the inline `$type` that
`build` already reads, and keeps it:

```python
@dataclass
class Shipped: on: date
@dataclass
class Cancelled: reason: str
@dataclass
class Order: event: Shipped | Cancelled

struct_of(Order).decode({"event": {"$type": "Shipped", "on": "2026-08-08"}})
# {'event': {'$type': 'Shipped', 'on': datetime.date(2026, 8, 8)}}
```

An unknown or missing discriminator leaves the dict undecoded, for `build` to
report.

## What decode leaves alone

* **Absent keys stay absent.** Filling a missing key is what a default is for,
  and `resolve` serves it — fresh, certified, at its own depth. Decode never
  runs a recipe.
* **Unknown keys travel through untouched**, so `resolve` still reports them as
  unexpected. Dropping them here would turn a rejected payload into an accepted
  one.
* **A root that is not a dict** — `None`, a list, a string, a number, a dataclass
  instance — is returned as it came, and `build` reports it.

## Fresh trees

`decode` never modifies the tree it is given, and never hands back a `dict` or
`list` it descended into: each of those is newly built, so the caller may keep the
input, modify the output, or both:

```python
wire = {"name": "Ana", "birthday": "2000-05-17"}
prepared = schema.decode(wire)
# wire is unchanged, and `prepared` is a new dict, not `wire`
```

Aliasing is not preserved: one dict referenced twice in the input becomes two
independent dicts in the output. A portable tree has no aliases to carry, and
`build` constructs separate instances from them anyway.

The promise is about `dict` and `list` exactly, which is all a portable tree has.
Everything else is passed along as it is — right for the strings and numbers a
portable tree is made of, and it means anything that had no business being there
comes back out as the same object rather than a copy.

That includes a `dict` or `list` **subclass**, and the consequence is worth
stating because it is easy to reach: `json.loads(text, object_pairs_hook=OrderedDict)`
produces a tree of `OrderedDict`, and decode does not descend into it or rebuild
it — it returns it untouched, restoring nothing, and `resolve` reports
`expected dict, got OrderedDict`.

That is the exact-type rule doing its job rather than an oversight. `resolve` and
`build` have always refused a `dict` subclass, and rebuilding one as a plain
`dict` would be decode turning a subclass into its base — the one thing the
no-coercion rule forbids, and it would make validation accept a tree it is
supposed to reject. Producing a plain portable tree is the caller's side of the
boundary: drop the hook, or convert before decoding.

Decode walks the tree recursively, so input the interpreter's stack cannot follow
raises `RecursionError`: a cycle, and equally a finite tree a few thousand lists
deep, which is legitimate JSON. That limit is the same everywhere else in the
core — see [restrictions.md](restrictions.md).

## Order

`decode` runs before `resolve` and `build`, never after. `resolve` fills absent
keys with real Python objects — dates, enum members, dataclass instances — which
are not portable data; decoding them again would be meaningless. The pipeline has
one direction:

```python
schema.build(schema.decode(data))
```

There is no shortcut that does both. The boundary is worth seeing at the call
site: one step recovers what the transport lost, the other decides whether the
result satisfies the contract, and only the second one can fail.

For a value already in exact Python — a default, a test fixture, a value built in
Python — `decode` is unnecessary and `build` takes it directly. Decoding it is
harmless: nothing in an exact tree matches a portable spelling that isn't already
its own.

# The portable contract

`Struct.to_dict()` and `Signature.to_dict()` write the compiled schema as a
portable tree — dicts, lists, strings, numbers, booleans and null, and nothing
else. It is the contract as data: what the schema accepts, and nothing about how
anyone should present it.

```python
import json
from dataclasses import dataclass
from datetime import date
from pytypehint import struct_of

@dataclass
class User:
    name: str
    birthday: date

json.dumps(struct_of(User).to_dict())
```

```json
{"v": 1, "kind": "struct", "root": "User",
 "defs": {"structs": {"User": {"name": "User", "fields": [
    {"name": "name", "shape": [{"type": "str"}]},
    {"name": "birthday", "shape": [{"type": "date"}]}]}},
          "enums": {}}}
```

## What it is for

The core compiles a contract; every wrapper has had to learn how to read it, and
each learned separately. A form generator, a command line, a client in another
language, a store that names a file after the shape of its rows — all of them
need the same description, and none of them needs the same presentation. This is
the description. Presentation stays where it belongs: `pytypehintweb` decides
what a control looks like, a CLI decides what a flag looks like, and the core
decides neither.

So the format carries no `inputType`, no widget, no HTML, no CSS, no ordering
hints, no layout, and none of the wording a medium invents for itself — the text
of a range error, the caption on a stepper, the label of an "add row" button.

What it does carry is every atom the *author* wrote, including the notation ones:
`Label`, `Description`, `Placeholder`, the message on a `Pattern`, and also
`Rows`, `Step`, `Slider` and `IsPassword`. None of those affect validation, and
naming them here is not a lapse — they are part of the closed vocabulary the core
admits precisely because several rendering contexts agree on what they mean, and
the author put them on the field deliberately. [atoms.md](atoms.md) sets the bar
they had to clear.

The line is not "does it concern presentation" but "who decided it". An author
writing `Rows(5)` is a fact about the field, and the document reports it. Whether
that becomes a textarea, a repeated flag or five lines of a TUI is the wrapper's
call, and the document says nothing about it.

Everything a particular medium needs beyond the contract travels through `Extra`,
which the core stores verbatim and never reads — see [atoms.md](atoms.md).

## Two guarantees

**It is deterministic.** Equal definitions produce equal documents, byte for
byte, across processes and hash seeds. Every key is written in a fixed order,
every sequence keeps the order the author wrote, and nothing derived from `id()`
or from set iteration reaches the output. `json.dumps` needs no `sort_keys`. That
is what makes the document usable as a fingerprint, a cache key, or the two sides
of a diff. Nothing outside the process is consulted at any point, and that holds
by construction rather than by care: there is no filesystem, no clock, no
environment and no working directory anywhere in the emission, because a compiled
schema itself holds nothing that was read from them. Even the one thing the format
decides rather than copies — which option of a slot a default inhabits — is
decided from the schema and the value alone.

```python
a = struct_of(User).to_dict()
b = struct_of(User).to_dict()
assert json.dumps(a) == json.dumps(b)
```

One caveat, and it belongs to the interpreter rather than to the emitter: a
signature's `doc` is the function's `__doc__`, and `python -OO` discards every
docstring, so under that flag the key is absent. Documents are comparable across
runs of the same interpreter configuration, not across a change of it.

**Each call returns a fresh tree.** Every dict and every list in the result is
new, at any depth, so the caller can rewrite the tree wherever it likes without
reaching the schema or the next call:

```python
document = schema.to_dict()
document["defs"]["structs"].clear()      # harmless
assert schema.to_dict() == original
```

Nothing is cached between calls. Two callers never receive the same tree.

The leaves are another matter, and deliberately so: a `label`, a `pattern`, a
`choices` entry and a text `default` are the very string objects the shape holds.
Sharing them is what makes the guarantee cheap instead of costly — a value that
cannot be mutated cannot be observed to be shared, so copying it would buy the
caller nothing it does not already have.

## It speaks decode's language

A date is written the way [`decode`](decode.md) reads one, an enum member by the
name decode looks up, and a value that would be ambiguous in a portable tree
carries the same `$type`/`$value` wrapper decode reads. So a default taken from
this document is valid input to the pipeline, with no translation in between:

```python
@dataclass
class Trip:
    leaves: date = date(2026, 8, 8)

schema = struct_of(Trip)
written = schema.to_dict()["defs"]["structs"]["Trip"]["fields"][0]["default"]
# "2026-08-08"
schema.build(schema.decode({"leaves": written}))     # Trip(leaves=date(2026, 8, 8))
```

`decode` alone already lands on the exact value in almost every case. Two
exceptions survive it, and both are removed by `build` rather than by `decode`,
because both are things validation still needs:

* a slot whose options share a Python runtime type keeps its wrapper. Those are
  exactly the slots with two or more `list` options — no other pair of options
  can share a Python type and still be distinguishable, so `duplicate option
  types` would have rejected them;
* a nested dataclass stays a dict until `build` constructs it, keeping its inline
  `$type` if it had one.

That is why the round trip is stated through `build`. One portable language,
written by `to_dict` and read by `decode`.

## Version

```json
{"v": 1, ...}
```

`v` rises only when a key already in the format changes meaning or leaves. New
keys do not raise it, so a reader must ignore keys it does not know — that is
what makes an addition compatible. `v` is the version of the *format*, never of
the library: emitting a library version would change every document on every
release and is provenance, not contract.

## Documents

Two kinds, told apart by `kind`.

```jsonc
{
  "v": 1,
  "kind": "struct",
  "root": "Cart",                 // an id in defs.structs
  "defs": {"structs": {…}, "enums": {…}}
}
```

```jsonc
{
  "v": 1,
  "kind": "signature",
  "name": "upload",               // an identifier
  "doc": "Upload a document.",    // omitted when the function has no docstring
  "params": [ <field>, … ],
  "defs": {"structs": {…}, "enums": {…}}
}
```

A struct's fields live in the table because a recursive field points back at the
root and needs somewhere to point. A signature's parameters are written in place,
because nothing can hold a reference to a signature.

`defs` is always present with both tables, even empty. It is the document's
skeleton rather than data, and a shape that varies would make every reader write
`doc.get("defs", {}).get("enums", {})`.

## Definitions

```jsonc
"structs": {
  "Cart": {
    "name": "Cart",               // cls.__name__ — the string the wire carries as $type
    "fields": [ <field>, … ]
  }
},
"enums": {
  "Role": {
    "name": "Role",
    "members": ["ADMIN", "USER"]  // canonical members, in definition order
  }
}
```

**Always a reference, never inlined.** A struct is written once and pointed at
from every occurrence. This is what makes recursion terminate and what keeps a
shared dataclass from being copied: a graph of twenty structs where each field
reuses the previous one has two million nodes if inlined, and twenty-one if
referenced. It also leaves one code path in the reader — resolve the id — instead
of "does this occurrence carry the definition or a pointer?".

**Ids and names are different things.** The `name` is contract: it is what
travels as `$type`. The id is a handle local to this document. They are usually
the same string, but two classes of the same name can sit in one schema whenever
they are not options of one field, and no name distinguishes them — two classes
built by the same factory share `__module__` and `__qualname__` too. So the id is
the class name made unique within the document by the order it was first reached:
`"Target"`, then `"Target#2"`. Read the `name`; use the id only to follow a `ref`.

Structs and enums have separate tables because they have separate discriminators:
a dataclass and an enum of the same class name never compete for one `$type`, and
the core admits that pair on purpose.

Enum members are names only. A member's value may be a tuple or an object, which
a portable tree cannot carry, and the name is what identifies a member anyway —
`EnumShape` accepts a member by its exact type, never by its value. Aliases are
left out: an alias names a member already listed, and `decode` still accepts one
because the enum resolves it to that member.

## Fields

```jsonc
{
  "name": "age",                  // always
  "label": "Age",                 // omitted when absent
  "description": "…",             // omitted when absent
  "optional_toggle": false,       // omitted when absent; false is written
  "default": 18,                  // omitted when there is no default
  "shape": [ <node>, … ]          // always an array, at least one, author's order
}
```

`shape` is an array even for a single option, so a reader has one code path
rather than two.

**There is no `optional` or `required` key.** Optionality means different things
to a form, to a patch endpoint and to a validator of raw payloads, and all three
are right — [philosophy.md](philosophy.md) declines to choose for them. The raw
structure does not opine: a `{"type": "none"}` among the options says one thing,
the presence of `default` says another, and the reader concludes. `to_dict` does
not decide where the core refuses to.

## Absence, `null`, and `false`

An absent atom omits its key. It is never written as `null`, because two
spellings of one fact would stop the document being canonical and break diffs,
hashes and comparisons.

`null` therefore means exactly one thing, in exactly one place: `"default": null`
says the default is `None`. A field with no default omits the key entirely, which
is how `MISSING` is expressed — the two are different states and both are real.

Values equal to their own default are omitted too — no `"exclusive_min": false`,
no `"extras": {}`. Three exceptions, each because the value is information:

* `"optional_toggle": false` — absent, true and false are three states;
* `"slider": {"show_value": false}` — the atom's actual value;
* `"file_hint": {}` — the mark itself, with nothing narrowing it.

## Shape nodes

`type` is one of `int`, `float`, `str`, `bool`, `date`, `time`, `none`, `list`,
`enum`, `struct`.

`id` is `Shape.option_id()` — the identity a discriminator names, from
[restrictions.md](restrictions.md). It is written only where the slot holds two
or more options, because that is the only place anything reads it.

An `id` is unique within its discriminator's namespace, which is what a sender
needs: the compiler rejects a repeat among the `struct` options and a repeat
among all the others. It is not unique across the two — a dataclass and an enum
of one class name are admissible together, and both write that name. Index
options by position; read `id` only to fill a discriminator.

```jsonc
{"type": "int",   "id": …, "min": 0, "exclusive_min": true,
                  "max": 10, "exclusive_max": true, "multiple_of": 5,
                  "choices": [0, 5, 10], "step": 5,
                  "slider": {"show_value": true}, "placeholder": "…", "extras": {…}}

{"type": "float", "id": …, "min": 0.0, "exclusive_min": true, "max": 1.0,
                  "exclusive_max": true, "choices": [0.5], "step": 0.01,
                  "slider": {"show_value": false}, "placeholder": "…", "extras": {…}}

{"type": "str",   "id": …, "min_length": 1, "max_length": 20,
                  "pattern": "…", "pattern_message": "…", "choices": ["a", "b"],
                  "file_hint": {"extensions": [".pdf"], "min_size": 0,
                                "max_size": 1048576},
                  "is_password": true, "rows": 5, "placeholder": "…", "extras": {…}}

{"type": "date",  "id": …, "min": "2024-01-01", "exclusive_min": true,
                  "max": "2024-12-31", "exclusive_max": true,
                  "choices": ["2024-06-01"], "placeholder": "…", "extras": {…}}

{"type": "time",  "id": …, "min": "09:00:00", "exclusive_min": true,
                  "max": "18:00:00", "exclusive_max": true,
                  "choices": ["09:00:00"], "placeholder": "…", "extras": {…}}

{"type": "bool",  "id": …, "extras": {…}}
{"type": "none",  "id": "None", "extras": {…}}

{"type": "list",  "id": …, "min_items": 0, "max_items": 10,
                  "item": [ <node>, … ], "extras": {…}}

{"type": "enum",  "id": …, "ref": "Role", "extras": {…}}
{"type": "struct","id": …, "ref": "Cart"}
```

A number on a `float` node is written as a float, so that `Min(0)` and `Min(0.0)`
— equal atoms — cannot produce two documents. The exception is an integer with no
float of equal value, and there are two ways to be one. An integer outside the
float range (`10**400`) names no float at all, and the shape rejects it as an
invalid atom when it compiles — on `min`, on `max` and on `step` alike — so it
never reaches a document. An integer inside the range may still not be
representable, because above `2**53` the floats thin out and `float()` answers
with a neighbour instead of failing; that one arrives here, through an ordinary
`Min` or `Max`, and is written exactly as it is. Publishing the neighbour would
state a bound the schema does not hold: `Min(2**53 + 1)` written as
`9007199254740992.0` invites a value the core then rejects as `too small`. JSON
has one number type, so in that case the distinction survives only until the
document is serialized.

A few names are deliberate:

* **`min_length` / `max_length` on `str`, `min_items` / `max_items` on `list`.**
  The core already fixed that a bound means a length there and rejects an
  exclusive one. Calling it `min` would invite a reader to render "minimum 3" over
  a text field. `exclusive_min` and `exclusive_max` cannot appear on either.
* **`item`, not `items`.** In JSON Schema an array under `items` means positional
  validation of a tuple. Here it is the set of options *one element* may take —
  the same word for two different things would be read wrong.
* **`ref`, not `$ref`.** In this project `$` marks reserved keys in *data*
  (`$type`, `$value`). Schema metadata does not borrow that convention.
* **`slider` is an object**, never a bare boolean: `show_value: false` would
  otherwise read as "no slider".
* **`extras` is last** on every node, and omitted when empty. Its keys are already
  sorted and unique. A `Struct` node never has extras; the vocabulary does not
  admit atoms on a nested dataclass.

`pattern` is a Python `re` pattern applied with `fullmatch`. It is portable as a
string and not necessarily portable as a regex — a consumer targeting another
engine must check it, as `pytypehintweb` does for the browser.

## Defaults

A default is written in the portable language of [decode.md](decode.md): a date
as `"YYYY-MM-DD"`, a time as `"HH:MM:SS"`, an enum member as its name, a list as
an array, a nested dataclass as an object.

Every certified default can be written this way. Compilation already proved that
its type, and the type of everything inside it, comes from the closed vocabulary,
so the encoding is total — there is no default the format has to omit, mark, or
fail on. A `default_factory` is not a special case: `Field.default` is the
certified *product*, and a portable tree has no aliasing to describe anyway.

Where two options of a slot share a portable spelling, the written value carries
the same wrapper `decode` consumes, so it names the option it belongs to. This is
a rule about a slot and not about a field, so it applies just as much to a list
element and to a field of a nested dataclass:

```jsonc
{"name": "limit", "default": {"$type": "int", "$value": 10},
 "shape": [{"type": "int", "id": "int"}, {"type": "float", "id": "float"}]}

{"name": "when", "default": {"$type": "date", "$value": "2024-06-01"},
 "shape": [{"type": "str", "id": "str"}, {"type": "date", "id": "date"}]}

{"name": "days", "default": [{"$type": "date", "$value": "2024-06-01"}],
 "shape": [{"type": "list",
            "item": [{"type": "str", "id": "str"}, {"type": "date", "id": "date"}]}]}
```

A dataclass default in a union of two or more dataclasses uses the inline `$type`
the core already uses, not the wrapper.

An impure recipe makes the written default a sample of one serving.
[defaults.md](defaults.md) already asks for purity and does not watch for it; the
format inherits that promise rather than restating it.

## Reading the wire from the document

Everything a sender needs is derivable from the document, and the rule is short.
To name an option unambiguously:

* a `struct` option in a slot with two or more `struct` options — send the object
  with `"$type": <name>` inside it;
* any other option in a slot where two or more options share a portable spelling
  — send `{"$type": <id>, "$value": <portable>}`;
* otherwise — send the bare portable value.

Two options share a portable spelling when they are written the same way: `int`
and `float` both as a number, and `str`, `date`, `time` and any `enum` all as a
string. Two lists, or two structs, share theirs by definition.

The named spelling always works. The bare one is shorter and works wherever it is
unambiguous — [decode.md](decode.md) sets out exactly when.

## What never appears

Implementation: the compiled `re.Pattern` behind `pattern`, the recipe behind a
default, the deferred-certification flag, the tuple form of `extras`, any method,
and the `MISSING` sentinel in any spelling — it is expressed by omitting `default`.

Python identity: class objects, `__module__`, `__qualname__`, `__doc__` of a
dataclass or enum, filesystem paths, `id()`, memory addresses, hashes, and enum
member values.

`repr()` of anything. [restrictions.md](restrictions.md) is explicit that an
option's identity is derived from the compiled shape and never from `repr()`, and
that holds for the whole format. `Struct.__repr__` exists to debug, not to travel.

Interpretation: `optional`, `required`, `nullable`, flattening, traversal
indexes, or the "real option" of an `X | None`.

Provenance: the library version, timestamps, hostnames, the working directory.

## Not a plan

`to_dict()` is not `pytypehintweb`'s plan and must not grow into it. The plan
converts exclusive bounds to inclusive ones for `<input>`, folds `int` and
`float` together because JavaScript writes `3.0` as `3`, carries every message
string a browser shows, and rejects combinations the core deliberately allows.
Each of those is a correct decision *about a browser*, and each would be wrong
for a CLI, for a queue consumer, or for another language. The core describes; the
wrapper decides.

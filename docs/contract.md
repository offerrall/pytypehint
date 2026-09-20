# Portable contract

`Struct.to_dict()` and `Signature.to_dict()` return a JSON-compatible schema tree.
The caller may serialize it with `json.dumps`. Every call returns fresh dicts and
lists. Equal definitions produce the same document across processes and hash
seeds, assuming deterministic defaults and the same interpreter configuration
(`python -OO` removes function docstrings).

## Document and definitions

```json
{
  "v": 1,
  "kind": "struct",
  "root": "User",
  "defs": {
    "structs": {
      "User": {
        "name": "User",
        "fields": [{"name": "name", "shape": [{"type": "str"}]}]
      }
    },
    "enums": {}
  }
}
```

A signature replaces `root` with `name`, optional function `doc`, and `params`
(an array of fields); its `kind` is `"signature"`. Both definition tables are
always present. Enum definitions contain `name` and `members`, an ordered array
of canonical member names; aliases and member values are omitted.

Struct and enum nodes always use `ref` into their respective definition tables.
Definitions are stored once, so recursive schemas terminate. IDs are local handles
assigned on first encounter: `User`, `User#2`, etc. Their `name` is the class name
used in data discriminators; consumers must not substitute the definition ID.

`v` versions the format, not the library. Removing a key or changing its meaning
raises `v`; additive keys do not. Ignore unknown keys and reject unsupported shape
types. Tuple nodes were added in library 1.1.0 while retaining format version 1;
consumers need tuple support to read them.

## Fields and nodes

A field has `name` and `shape` (a nonempty ordered array of option nodes).
Optional keys are `label`, `description`, `optional_toggle` and `default`.
No default means the key is absent; a `None` default is `"default": null`.
There are no `optional`, `required` or `nullable` keys: inspect `default` and
`{"type": "none"}` separately.

Each node has `type`. In a slot containing several options, each also has `id`,
its `Shape.option_id()`. IDs are unique within the dataclass namespace and within
the other-option namespace, not across both. Preserve option positions; use IDs
for discriminators. See [option identities](restrictions.md#option-identity).

| `type` | Additional keys when applicable |
|---|---|
| `int` | `min`, `max`, `exclusive_min`, `exclusive_max`, `multiple_of`, `choices`, `step`, `slider`, `placeholder`, `extras` |
| `float` | `min`, `max`, `exclusive_min`, `exclusive_max`, `choices`, `step`, `slider`, `placeholder`, `extras` |
| `str` | `min_length`, `max_length`, `pattern`, `pattern_message`, `choices`, `file_hint`, `is_password`, `rows`, `placeholder`, `extras` |
| `date`, `time` | `min`, `max`, `exclusive_min`, `exclusive_max`, `choices`, `placeholder`, `extras` |
| `bool`, `none` | `extras` |
| `list` | `item`, `min_items`, `max_items`, `extras` |
| `tuple` | `items` or `item`, `min_items`, `max_items`, `extras` |
| `enum` | `ref`, `extras` |
| `struct` | `ref` |

`item` is an option array for repeated elements. `items` is an array of option
arrays for fixed tuple positions; `items: []` describes `tuple[()]`. They never
coexist. A tuple with `item` is variadic.

```json
{"type": "tuple", "items": [[{"type": "int"}], [{"type": "str"}]]}
```

`slider` is `{"show_value": true}` or `{"show_value": false}`.
`file_hint` may contain `extensions` (array), `min_size` and `max_size` (bytes).
`extras` is a dictionary of string pairs sorted by key, omitted when empty.
`pattern` is a Python `re.fullmatch` expression; consumers using other regex
engines must check compatibility.

Absent atoms and default-valued flags are omitted, including false exclusive
bounds. Exceptions preserving explicit notation are `optional_toggle: false`,
`slider: {"show_value": false}` and `file_hint: {}`. Dates use `YYYY-MM-DD`;
times use `HH:MM:SS`. Float atom numbers normalize to floats when exactly
representable; integer bounds with no equal float remain integers. Atom signed
zero normalizes to positive zero; a default's signed zero is preserved.

## Values and defaults

Defaults use [decode](decode.md)'s portable spelling: dates and times as strings,
enums by member name, lists and tuples as arrays, dataclasses as objects.
Factories contribute their certified product, not executable recipes.
A field default taken from the document round-trips through
`schema.build(schema.decode(data))`, subject to the author's
[default purity requirements](defaults.md).

To select an option when writing portable values:

| Slot | Encoding |
|---|---|
| Multiple dataclasses | Object with inline `"$type": <class name>` |
| Other options sharing a portable spelling | `{"$type": <option id>, "$value": <portable value>}` |
| Unambiguous option | Bare portable value |

Numbers share a spelling between `int` and `float`; strings between `str`,
`date`, `time` and enums; arrays between lists and tuples. The rule applies to
fields and sequence slots. Exported defaults include the needed discriminators:

```json
{"name": "limit", "default": {"$type": "float", "$value": 3.0},
 "shape": [{"type": "int", "id": "int"}, {"type": "float", "id": "float"}]}
```

The document contains declared constraints and notation, not rendering decisions,
Python objects, recipes, library versions or runtime provenance. File size
constraints are declared here and enforced by the consumer holding the file.

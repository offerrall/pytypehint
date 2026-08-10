# Comparison

| Capability | pytypehint core | Wrapper | Dataclasses alone |
|---|---:|---:|---:|
| Compile type hints into inspectable shapes | yes | consumes | no |
| Export the contract as portable data | yes | consumes | no |
| Recover exact Python from a portable tree | yes | consumes | no |
| Exact validation and error paths | yes | may present | no |
| Cross-check atom contradictions at import | yes | no | no |
| Fresh rematerialized defaults | yes | consumes | factories only |
| Construct nested dataclasses from data | yes | calls | no |
| Parse or emit JSON text | no | yes | no |
| Coerce HTTP/CLI/form input | no | yes | no |
| Render controls | no | yes | no |
| Accumulate every failure in a tree | no | yes | no |
| Interpret the schema (optionality, traversal) | no | yes | no |
| Execute or await functions | no | yes | normal Python |
| Check that a file exists, its kind and its size | no | yes | no |

The core column is the contract: describing it, recovering values written in its
portable form, validating them and constructing from them. It stops there.

The two new rows are worth reading against the two below them. Writing the
contract down is not rendering it, and recovering a `date` spelled as
`"2026-08-08"` is not deciding that `"12"` was meant as a number. The first pair
is determined by the schema alone; the second pair needs to know what medium
wrote the value, which is exactly what the core does not know. See
[philosophy.md](philosophy.md) and [decode.md](decode.md).

The last row is where the line is drawn in the wrong place most often. A `str`
marked with `FileHint` declares the extensions the file may take and the sizes it
must fall between; the core validates the extension, which is a fact about the
text it was handed and nothing else, and writes the sizes into the portable
document without checking them. A library that validates the file itself — that
it exists, that it is a regular file, that it weighs less than ten megabytes — is
answering a question about one machine at one instant, and the answer expires as
it is given, so whoever opens the file has to ask again regardless. The core
promises what it can keep, and the boundary that receives the upload or reads the
command-line argument enforces the rest. See
[philosophy.md](philosophy.md).

The wrapper column need not be a single wrapper: coercion, presentation,
inspection ergonomics and error accumulation may live in the wrapper itself or in
an intermediate package that depends on the core and versions its own
conveniences on its own schedule.

## When not to use it

Do not use pytypehint when input is already trusted Python objects, when coercion
is the primary task and no wrapper boundary exists, or when the required types
fall outside its closed vocabulary. Direct dataclass construction is simpler for
internal code without an external-data boundary.

## Cost

Compile schemas once and share them. Compilation resolves hints, checks atoms and
certifies defaults. `build` then validates the supplied tree once and constructs
directly from it; missing defaults are rematerialized and validated at their own
level. Every value is validated exactly once, so the cost is linear in the size
of the input.

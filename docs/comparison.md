# Comparison

| Capability | pytypehint core | Wrapper | Dataclasses alone |
|---|---:|---:|---:|
| Compile type hints into inspectable shapes | yes | consumes | no |
| Exact validation and error paths | yes | may present | no |
| Cross-check atom contradictions at import | yes | no | no |
| Fresh rematerialized defaults | yes | consumes | factories only |
| Construct nested dataclasses from data | yes | calls | no |
| Coerce HTTP/CLI/form input | no | yes | no |
| Render controls | no | yes | no |
| Accumulate every failure in a tree | no | yes | no |
| Interpret the schema (optionality, traversal) | no | yes | no |
| Execute or await functions | no | yes | normal Python |

The core column is schema, validation and construction, and stops there. The
wrapper column need not be a single wrapper: coercion, presentation, inspection
ergonomics and error accumulation may live in the wrapper itself or in an
intermediate package that depends on the core and versions its own conveniences
on its own schedule. See [philosophy.md](philosophy.md).

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

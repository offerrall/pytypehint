# Guarantees

- Exact validation, with explicit selection for ambiguous unions; no guessing
  from contents or implicit coercion. See [build](build.md).
- The first schema error includes its full field/index path in both its message
  and `path`, with the reason in `leaf`.
- Defaults are certified at compilation and validated at every missing-key
  serving. Reconstructed contents are fresh; factories must honor the author's
  [purity requirements](defaults.md).
- `resolve` validates recursively, preserves supplied values by reference and
  fills defaults only at the current level. `build` constructs nested instances.
- `decode` does not mutate input, fill defaults or discard unknown keys. It
  rebuilds traversed plain containers; actual tuples and subclasses pass through.
- `to_dict()` returns a fresh tree with deterministic ordering. Deterministic
  defaults and matching interpreter configuration are required for equal output.
- The core's checks depend on the schema and value. File access and other external
  checks belong to the consumer; user factories and constructors remain user code.
- `Signature.build` prepares kwargs and never calls the function.

`@immutable` additionally validates construction and restricts fields to deeply
immutable values, allowing already validated children to be reused without
traversing them again. See [its contract and limits](immutable.md).

For accepted definitions and runtime limits, see [restrictions](restrictions.md).

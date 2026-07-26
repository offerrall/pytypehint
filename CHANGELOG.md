# Changelog

## [0.0.7]

- Breaking: `IsPathFile` now guarantees that the string names a real file at the
  moment of validation, not merely that its text ends in an accepted suffix. A
  value such as `"missing.png"` previously passed on its extension alone and now
  fails with `file does not exist: 'missing.png'`. The mark validates, in this
  order: the value is exactly `str`, the ordinary `Str` limits on the text, the
  extension, `stat`, that the target is a regular file and not a directory, the
  size, and finally `Choices`. The extension is checked before the filesystem
  because it costs nothing and names the defect precisely.
- `IsPathFile` gains `min_size` and `max_size`, byte counts that are `int` or
  `None`, never negative, with `min_size` not exceeding `max_size`; `bool` is not
  accepted as an `int`. Violations report
  `IsPathFile.min_size must be int or None, got bool`,
  `IsPathFile.max_size must be >= 0, got -1` and
  `IsPathFile: min_size 100 exceeds max_size 50`. A file whose size falls outside
  the bounds fails with `file too small: 120 bytes, minimum 1024` or
  `file too large: 7000000 bytes, maximum 5242880`; an empty file is valid unless
  `min_size` is greater than zero.
- The public value remains exactly `str`. `pathlib.Path` is used only inside the
  validation, to inspect the file: nothing is coerced to `Path`, normalized,
  resolved, expanded or made absolute, so a relative path keeps its meaning
  relative to the working directory and the value stays as written.
- New failures: `file does not exist: <path>`, `not a file: <path>` for a
  directory or any non-regular target, the two size messages above, and
  `cannot inspect file <path>: <error type>: <error>` when the OS refuses the
  inspection. `FileNotFoundError` is distinguished from every other `OSError`, and
  each failure keeps its cause through `raise ... from` and its coordinate in
  `path`/`leaf` — `document: file does not exist: 'missing.pdf'`,
  `files: [1]: file too large: 7000000 bytes, maximum 5242880`.
- `Path.stat()` follows symlinks: a live link to a regular file is accepted and a
  broken one fails as non-existent. The guarantee is bounded in time — the file
  existed and met the contract when it was validated, and nothing promises it
  still does afterwards.
- Breaking: `Choices` combined with `IsPathFile` are certified against the whole
  file contract when the schema compiles, where before only their extension was
  checked. `Str.choices: file does not exist: 'default.png'` now fails
  compilation. Defaults are certified the same way, so a `signature_of` over
  `image: Annotated[str, IsPathFile()] = "default.png"` fails unless that file
  exists, is a regular file and meets the extension and size bounds.
- One internal function validates the whole contract, so `_check`, `Choices` and
  default certification cannot drift apart. `IsPathFile` remains metadata
  exclusive to `Str`: no new shape, no `PathFile` type, and no compatibility
  switch (`exists=False`, `strict=False`) — the semantics are single and explicit.

## [0.0.6]

- Breaking: `datetime.time` values with non-zero microseconds are no longer
  accepted. Time precision is limited to whole seconds, so the effective range
  is `00:00:00..23:59:59`. A value previously admissible such as
  `time(12, 30, 0, 500000)` now fails with `time precision is limited to whole
  seconds`. The rule is enforced at every entry point of the core: `Min`/`Max`
  bounds and `Choices` members at compile time, and a value wherever it is
  validated — direct check, default certification, `resolve`, `build`, and
  inside nested dataclasses, unions and lists — through the single `Time._check`.
  The failure carries its coordinate as `path`, like every other constraint.
- Following from the tighter range, `Time`'s exclusive-edge guard moves in from
  the sub-second clock edge to the whole-second one: an exclusive `Min` at
  `23:59:59` (was `time.max`) and an exclusive `Max` at `00:00:00` now report
  `exclusive bound at ... leaves no valid time`. A bound at `time.max` is instead
  rejected as sub-second precision.

## [0.0.5]

- Compilation now rejects a union of two enums that share a class name, e.g.
  two Enum classes both named `Color`, with `Field '<name>': duplicate
  discriminator name(s): Color` — the same message and recursion (into `list`
  items) that already guarded homonym dataclasses. Both options collapse to one
  `option_id()`, the public identity wrappers read to name an option, and one
  identity for two options is a defective schema. The core still routes each by
  its exact member type; the rule is about identity, not routing, so an enum and
  a dataclass of the same name never collide and stay admissible. Previously the
  core admitted the pair and only a wrapper could catch it.

## [0.0.4]

- Enum fields now accept `Extra`, the same namespaced wrapper-notation channel
  the other leaf shapes already carry. `EnumShape` gains `_extras` and a
  read-only `extras` dict; any other atom on an enum still reports `unsupported
  metadata for enum`. Dataclass (`Struct`) fields stay closed — annotate their
  fields, not the nesting.
- `Time` now rejects an exclusive bound at the clock's edge at compile time —
  `Min(time.max, exclusive=True)` and `Max(time.min, exclusive=True)` — with
  `exclusive bound at ... leaves no valid time`, symmetric with the `Date` edge.
  These bounds previously compiled while admitting no value. `Float`'s analogous
  edge is left under the "no general satisfiability" doctrine.
- `check_options_value` now attaches a PEP 678 note per candidate to a `matches
  no option` error, recording why each option rejected the value (`as <id>:
  <cause>`). The main message, `leaf` and `path` are unchanged; the notes survive
  pickle.
- Breaking (messages only): compile-time certification of an invalid default now
  reports the failure as structured data — `path` carries the field name,
  `"default"`, and any sub-path as clean coordinates, with the violation as the
  `leaf`. The rendered line reads `x: default: <leaf>`, **identical** to the
  runtime serving path (`_resolve_fields`): the same defect now reads the same
  way whether certification or serving catches it. Previously certification
  degraded the whole line into the leaf and rendered `Field 'x': default <leaf>`.
  Only the message and its structure changed; no behaviour did.

## [0.0.3]

- Unions whose options share one runtime input type now compile. `list[str] |
  list[int]` was rejected as a duplicate; both options are valid Python and
  describe different things, so the core admits them.
- Such a value selects its option through a discriminated wrapper:
  `{"$type": "list[str]", "$value": ["a", "b"]}`. `$type` is the option
  identity — `list[str]`, `list[int]`, `list[list[str]]` — and `$value` is the
  payload. The wrapper accepts no other key.
- The wrapper is required only where routing by exact runtime type is
  ambiguous. `int | str`, `list[str | int]`, `list[int] | None` and every other
  hint that already routed itself are unchanged and take no discriminator; an
  option that is alone in its runtime type does not accept one either.
- Dataclass unions keep the inline `$type` of 0.0.2 unchanged, at every depth
  and inside list items.
- Compilation still rejects options that stay indistinguishable with a
  discriminator — `list[Annotated[int, Min(0)]] | list[Annotated[int, Max(9)]]`
  share both a runtime type and an identity.
- `Shape.option_id()` returns that identity, for wrappers that need to offer the
  choice.
- No breaking change: every hint accepted by 0.0.2 compiles and behaves as
  before.

## [0.0.2]

- `Extra(value)` becomes `Extra(key, value)`, with a namespaced key
  (`"package.name"`) and any string value, empty included.
- Shapes replace `extra` with `extras`, a read-only `dict[str, str]` merged from
  every `Extra` atom on the hint. Keys layer independently: the outer atom wins.

## [0.0.1] - 2026-07-15

- Initial release.

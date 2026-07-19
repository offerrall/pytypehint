# Changelog

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

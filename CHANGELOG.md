# Changelog

## [0.0.2]

- `Extra(value)` becomes `Extra(key, value)`, with a namespaced key
  (`"package.name"`) and any string value, empty included.
- Shapes replace `extra` with `extras`, a read-only `dict[str, str]` merged from
  every `Extra` atom on the hint. Keys layer independently: the outer atom wins.

## [0.0.1] - 2026-07-15

- Initial release.

# Scope and ecosystem

| Task | Responsible layer |
|---|---|
| Define ordinary models | Python dataclasses and type hints |
| Inspect/export schemas, validate values, restore portable types, construct models | pytypehint |
| Parse JSON, coerce form/CLI input, render controls, collect multiple errors | Consumer |
| Call functions, check files, manage persistence/authentication | Application |

Direct dataclass construction is simpler for trusted internal objects. Use
pytypehint when you need strict input validation or a shared inspectable contract.
Compile once and reuse schemas.

Optional consumers, maintained separately:

- [pytypehintweb](https://github.com/offerrall/pytypehintweb): browser forms.
- [FuncToWeb](https://github.com/offerrall/FuncToWeb): web interfaces for functions.
- [pytypehintstore](https://github.com/offerrall/pytypehintstore): validated storage.

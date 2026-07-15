from dataclasses import dataclass

from pytypehint.structure import Field, _build_kwargs, _resolve_fields


@dataclass(frozen=True, kw_only=True, eq=False)
class Signature:
    name: str
    doc: str | None = None
    params: tuple[Field, ...] = ()

    def __post_init__(self):
        if type(self.name) is not str:
            raise TypeError(f"Signature.name must be str, got {type(self.name).__name__}")
        if not self.name.isidentifier():
            raise ValueError(f"Signature.name must be an identifier, got {self.name!r}")
        if self.doc is not None and type(self.doc) is not str:
            raise TypeError(f"Signature.doc must be str or None, got {type(self.doc).__name__}")
        if type(self.params) is not tuple or any(type(p) is not Field for p in self.params):
            raise TypeError("Signature.params must be a tuple of Field")
        names = [p.name for p in self.params]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate parameter names in {self.name}")

    def resolve(self, kwargs) -> dict:
        return _resolve_fields(self.params, kwargs, kind="argument")

    def build(self, kwargs) -> dict:
        return _build_kwargs(self.params, self.resolve(kwargs))

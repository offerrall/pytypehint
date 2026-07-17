import re
from dataclasses import dataclass, field
from datetime import date, time

from pytypehint.utils import type_name


_ORDERED = (int, float, date, time)


@dataclass(frozen=True)
class Min:
    value: int | float | date | time
    exclusive: bool = field(default=False, kw_only=True)

    def __post_init__(self):
        name = type_name(self)
        if type(self.value) not in _ORDERED:
            raise TypeError(f"{name}.value must be orderable (int, float, date or time), got {type(self.value).__name__}")

        if type(self.exclusive) is not bool:
            raise TypeError(f"{name}.exclusive must be bool, got {type(self.exclusive).__name__}")


@dataclass(frozen=True)
class Max:
    value: int | float | date | time
    exclusive: bool = field(default=False, kw_only=True)

    def __post_init__(self):
        name = type_name(self)
        if type(self.value) not in _ORDERED:
            raise TypeError(f"{name}.value must be orderable (int, float, date or time), got {type(self.value).__name__}")

        if type(self.exclusive) is not bool:
            raise TypeError(f"{name}.exclusive must be bool, got {type(self.exclusive).__name__}")


@dataclass(frozen=True)
class Label:
    value: str

    def __post_init__(self):
        name = type_name(self)
        if type(self.value) is not str:
            raise TypeError(f"{name}.value must be str, got {type(self.value).__name__}")

        if not self.value:
            raise ValueError(f"{name}.value must not be empty")


@dataclass(frozen=True)
class Description:
    value: str

    def __post_init__(self):
        name = type_name(self)
        if type(self.value) is not str:
            raise TypeError(f"{name}.value must be str, got {type(self.value).__name__}")

        if not self.value:
            raise ValueError(f"{name}.value must not be empty")


@dataclass(frozen=True)
class Step:
    value: int | float

    def __post_init__(self):
        name = type_name(self)
        if type(self.value) not in (int, float):
            raise TypeError(f"{name}.value must be a number, got {type(self.value).__name__}")

        if self.value <= 0:
            raise ValueError(f"{name}.value must be > 0, got {self.value}")


@dataclass(frozen=True, kw_only=True)
class Slider:
    show_value: bool = True

    def __post_init__(self):
        if type(self.show_value) is not bool:
            raise TypeError(f"{type_name(self)}.show_value must be bool, got {type(self.show_value).__name__}")


@dataclass(frozen=True)
class Placeholder:
    value: str

    def __post_init__(self):
        name = type_name(self)
        if type(self.value) is not str:
            raise TypeError(f"{name}.value must be str, got {type(self.value).__name__}")

        if not self.value:
            raise ValueError(f"{name}.value must not be empty")


@dataclass(frozen=True)
class Extra:
    key: str
    value: str

    def __post_init__(self):
        name = type_name(self)
        if type(self.key) is not str:
            raise TypeError(f"{name}.key must be str, got {type(self.key).__name__}")

        if not self.key:
            raise ValueError(f"{name}.key must not be empty")

        # The dot names the package that owns the key: several wrappers annotate
        # one field, and provenance is what keeps their keys apart.
        if "." not in self.key:
            raise ValueError(f"{name}.key must be namespaced ('package.name'), got {self.key!r}")

        # Unlike its sibling atoms the value may be empty: the core stores it and
        # never reads it, so what emptiness means is the wrapper's business.
        if type(self.value) is not str:
            raise TypeError(f"{name}.value must be str, got {type(self.value).__name__}")


@dataclass(frozen=True, kw_only=True)
class Choices:
    values: tuple[int | float | str | date | time, ...]

    def __post_init__(self):
        name = type_name(self)
        if type(self.values) is not tuple:
            raise TypeError(f"{name}.values must be tuple, got {type(self.values).__name__}")

        if not self.values:
            raise ValueError(f"{name}.values must not be empty")

        # Type belongs to the key because Python equates 1, 1.0 and True.
        keys = [(type(v), v) for v in self.values]
        try:
            if len(keys) != len(set(keys)):
                raise ValueError(f"{name}.values must not repeat")
        except TypeError:
            raise TypeError(f"{name}.values must be hashable") from None


@dataclass(frozen=True)
class MultipleOf:
    value: int

    def __post_init__(self):
        name = type_name(self)
        if type(self.value) is not int:
            raise TypeError(f"{name}.value must be int, got {type(self.value).__name__}")

        if self.value <= 0:
            raise ValueError(f"{name}.value must be > 0, got {self.value}")


@dataclass(frozen=True)
class Pattern:
    value: str
    message: str | None = field(default=None, kw_only=True)

    def __post_init__(self):
        name = type_name(self)
        if type(self.value) is not str:
            raise TypeError(f"{name}.value must be str, got {type(self.value).__name__}")

        if not self.value:
            raise ValueError(f"{name}.value must not be empty")

        try:
            re.compile(self.value)
        except re.error as e:
            raise ValueError(f"{name}.value is not a valid regex: {e}") from e

        if self.message is not None:
            if type(self.message) is not str:
                raise TypeError(f"{name}.message must be str, got {type(self.message).__name__}")

            if not self.message:
                raise ValueError(f"{name}.message must not be empty")


@dataclass(frozen=True, kw_only=True)
class IsPassword:
    pass


@dataclass(frozen=True)
class Rows:
    value: int

    def __post_init__(self):
        name = type_name(self)
        if type(self.value) is not int:
            raise TypeError(f"{name}.value must be int, got {type(self.value).__name__}")

        if self.value <= 0:
            raise ValueError(f"{name}.value must be > 0, got {self.value}")


@dataclass(frozen=True, kw_only=True)
class IsPathFile:
    extensions: tuple[str, ...] = ()

    def __post_init__(self):
        name = type_name(self)
        if type(self.extensions) is not tuple:
            raise TypeError(f"{name}.extensions must be tuple, got {type(self.extensions).__name__}")

        for e in self.extensions:
            if type(e) is not str:
                raise TypeError(f"{name}.extensions: expected str, got {type(e).__name__}")

            if not e.startswith("."):
                raise ValueError(f"{name}.extensions: {e!r} must start with '.'")

            if e != e.lower():
                raise ValueError(f"{name}.extensions: {e!r} must be lowercase")

        if len(self.extensions) != len(set(self.extensions)):
            raise ValueError(f"{name}.extensions must not repeat")


@dataclass(frozen=True)
class OptionalToggle:
    enabled: bool

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise TypeError(f"{type_name(self)}.enabled must be bool, got {type(self.enabled).__name__}")

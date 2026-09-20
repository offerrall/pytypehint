import math
import re
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from enum import Enum, Flag
from typing import ClassVar, cast

from pytypehint.atoms import (
    Choices, Min, Max, MultipleOf, Pattern, FileHint, IsPassword, Rows,
    Step, Slider, Placeholder,
)
from pytypehint.errors import SchemaTypeError, SchemaValueError, _prefixed
from pytypehint.utils import check_opt, render_number, type_name
from pytypehint.validation import check_options_value


def _finite(value) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _normalize_extras(owner: str, value) -> tuple[tuple[str, str], ...]:
    if type(value) is not tuple:
        raise TypeError(f"{owner}._extras must be tuple, got {type(value).__name__}")

    for pair in value:
        if (type(pair) is not tuple or len(pair) != 2
                or any(type(s) is not str for s in pair)):
            raise TypeError(f"{owner}._extras: expected a (key, value) pair of str, got {pair!r}")

    keys = [k for k, _ in value]
    if len(set(keys)) != len(keys):
        raise ValueError(f"{owner}._extras must not repeat keys")

    return tuple(sorted(value))


class Shape:
    pytype: ClassVar[type]

    discriminator: ClassVar[str] = "wrapper"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "pytype"):
            raise TypeError(f"{cls.__name__} must declare pytype")

    def _check(self, value) -> None:
        raise NotImplementedError(f"{type(self).__name__} must implement check")

    def option_id(self) -> str:
        return self.pytype.__name__


def duplicate_discriminators(shapes) -> list[str]:
    tables: dict[str, dict[str, set[type]]] = {}
    for shape in shapes:
        table = tables.setdefault(shape.discriminator, {})
        table.setdefault(shape.option_id(), set()).add(shape.pytype)

    duplicates = []
    for namespace in ("struct", "wrapper"):
        duplicates += sorted(option_id
                             for option_id, pytypes in tables.get(namespace, {}).items()
                             if len(pytypes) > 1)
    return duplicates


def duplicate_options(shapes) -> bool:
    seen: dict[type, set[str]] = {}
    for shape in shapes:
        ids = seen.setdefault(shape.pytype, set())
        option_id = shape.option_id()
        if option_id in ids:
            return True
        ids.add(option_id)
    return False


@dataclass(frozen=True, kw_only=True)
class Int(Shape):
    pytype: ClassVar[type] = int
    min: Min | None = None
    max: Max | None = None
    choices: Choices | None = None
    multiple_of: MultipleOf | None = None
    step: Step | None = None
    slider: Slider | None = None
    placeholder: Placeholder | None = None
    _extras: tuple[tuple[str, str], ...] = ()

    @property
    def extras(self) -> dict[str, str]:
        return dict(self._extras)

    def __post_init__(self):
        name = type_name(self)

        check_opt(name, "min", self.min, Min)
        check_opt(name, "max", self.max, Max)
        check_opt(name, "choices", self.choices, Choices)
        check_opt(name, "multiple_of", self.multiple_of, MultipleOf)
        check_opt(name, "step", self.step, Step)
        check_opt(name, "slider", self.slider, Slider)
        check_opt(name, "placeholder", self.placeholder, Placeholder)
        object.__setattr__(self, "_extras", _normalize_extras(name, self._extras))

        if self.min is not None and type(self.min.value) is not int:
            raise TypeError(f"{name}.min: expected int, got {type(self.min.value).__name__}")

        if self.max is not None and type(self.max.value) is not int:
            raise TypeError(f"{name}.max: expected int, got {type(self.max.value).__name__}")

        if self.step is not None and type(self.step.value) is not int:
            raise TypeError(f"{name}.step: expected int, got {type(self.step.value).__name__}")

        lo = None
        hi = None
        if self.min is not None:
            lo = self.min.value + 1 if self.min.exclusive else self.min.value
        if self.max is not None:
            hi = self.max.value - 1 if self.max.exclusive else self.max.value

        if lo is not None and hi is not None and lo > hi:
            raise ValueError(f"{name}: empty range ({render_number(self.min.value)}..{render_number(self.max.value)})")

        if self.choices is not None:
            for c in self.choices.values:
                if type(c) is not int:
                    raise TypeError(f"{name}.choices: expected int, got {type(c).__name__}")

                if lo is not None and c < lo:
                    raise ValueError(f"{name}.choices: {render_number(c)} below minimum {render_number(self.min.value)}")

                if hi is not None and c > hi:
                    raise ValueError(f"{name}.choices: {render_number(c)} above maximum {render_number(self.max.value)}")

        if self.multiple_of is not None:
            m = self.multiple_of.value

            if self.choices is not None:
                for c in self.choices.values:
                    if c % m != 0:
                        raise ValueError(f"{name}.choices: {render_number(c)} is not a multiple of {render_number(m)}")

            if lo is not None and hi is not None:
                smallest = -(-lo // m) * m
                if smallest > hi:
                    raise ValueError(
                        f"{name}: no multiple of {render_number(m)} in range ({render_number(self.min.value)}..{render_number(self.max.value)})")

        if self.slider is not None and (self.min is None or self.max is None):
            raise ValueError(f"{name}: slider requires min and max")

    def _check(self, value) -> None:
        if type(value) is not int:
            raise SchemaTypeError(f"expected int, got {type(value).__name__}")

        if self.min is not None:
            minimum = cast(int, self.min.value)
            if self.min.exclusive:
                if value <= minimum:
                    raise SchemaValueError(f"too small: {render_number(value)}, minimum {render_number(self.min.value)} (exclusive)")
            elif value < minimum:
                raise SchemaValueError(f"too small: {render_number(value)}, minimum {render_number(self.min.value)}")

        if self.max is not None:
            maximum = cast(int, self.max.value)
            if self.max.exclusive:
                if value >= maximum:
                    raise SchemaValueError(f"too large: {render_number(value)}, maximum {render_number(self.max.value)} (exclusive)")
            elif value > maximum:
                raise SchemaValueError(f"too large: {render_number(value)}, maximum {render_number(self.max.value)}")

        if self.multiple_of is not None and value % self.multiple_of.value != 0:
            raise SchemaValueError(f"not a multiple of {render_number(self.multiple_of.value)}: {render_number(value)}")

        if self.choices is not None and value not in self.choices.values:
            raise SchemaValueError(f"not a choice: {render_number(value)}, expected one of {render_number(self.choices.values)}")


@dataclass(frozen=True, kw_only=True)
class Float(Shape):
    pytype: ClassVar[type] = float
    min: Min | None = None
    max: Max | None = None
    choices: Choices | None = None
    step: Step | None = None
    slider: Slider | None = None
    placeholder: Placeholder | None = None
    _extras: tuple[tuple[str, str], ...] = ()

    @property
    def extras(self) -> dict[str, str]:
        return dict(self._extras)

    def __post_init__(self):
        name = type_name(self)

        check_opt(name, "min", self.min, Min)
        check_opt(name, "max", self.max, Max)
        check_opt(name, "choices", self.choices, Choices)
        check_opt(name, "step", self.step, Step)
        check_opt(name, "slider", self.slider, Slider)
        check_opt(name, "placeholder", self.placeholder, Placeholder)
        object.__setattr__(self, "_extras", _normalize_extras(name, self._extras))

        if self.min is not None and type(self.min.value) not in (int, float):
            raise TypeError(f"{name}.min: expected int or float, got {type(self.min.value).__name__}")

        if self.max is not None and type(self.max.value) not in (int, float):
            raise TypeError(f"{name}.max: expected int or float, got {type(self.max.value).__name__}")

        if self.min is not None and not _finite(self.min.value):
            raise ValueError(f"{name}.min: must be finite, got {render_number(self.min.value)}")

        if self.max is not None and not _finite(self.max.value):
            raise ValueError(f"{name}.max: must be finite, got {render_number(self.max.value)}")

        if self.step is not None and type(self.step.value) not in (int, float):
            raise TypeError(
                f"{name}.step: expected int or float, got {type(self.step.value).__name__}")

        if self.step is not None and not _finite(self.step.value):
            raise ValueError(f"{name}.step: must be finite, got {render_number(self.step.value)}")

        if self.min is not None and self.max is not None:
            empty = self.min.value > self.max.value or (
                self.min.value == self.max.value
                and (self.min.exclusive or self.max.exclusive))
            if empty:
                raise ValueError(f"{name}: empty range ({render_number(self.min.value)}..{render_number(self.max.value)})")

        if self.choices is not None:
            for c in self.choices.values:
                if type(c) is not float:
                    raise TypeError(f"{name}.choices: expected float, got {type(c).__name__}")

                if not math.isfinite(c):
                    raise ValueError(f"{name}.choices: must be finite, got {c}")

                if self.min is not None:
                    below = c <= self.min.value if self.min.exclusive else c < self.min.value
                    if below:
                        raise ValueError(f"{name}.choices: {c} below minimum {self.min.value}")

                if self.max is not None:
                    above = c >= self.max.value if self.max.exclusive else c > self.max.value
                    if above:
                        raise ValueError(f"{name}.choices: {c} above maximum {self.max.value}")

        if self.slider is not None and (self.min is None or self.max is None):
            raise ValueError(f"{name}: slider requires min and max")

    def _check(self, value) -> None:
        if type(value) is not float:
            raise SchemaTypeError(f"expected float, got {type(value).__name__}")

        if not math.isfinite(value):
            raise SchemaValueError(f"not finite: {value}")

        if self.min is not None:
            minimum = cast(int | float, self.min.value)
            if self.min.exclusive:
                if value <= minimum:
                    raise SchemaValueError(f"too small: {value}, minimum {self.min.value} (exclusive)")
            elif value < minimum:
                raise SchemaValueError(f"too small: {value}, minimum {self.min.value}")

        if self.max is not None:
            maximum = cast(int | float, self.max.value)
            if self.max.exclusive:
                if value >= maximum:
                    raise SchemaValueError(f"too large: {value}, maximum {self.max.value} (exclusive)")
            elif value > maximum:
                raise SchemaValueError(f"too large: {value}, maximum {self.max.value}")

        if self.choices is not None and value not in self.choices.values:
            raise SchemaValueError(f"not a choice: {value}, expected one of {self.choices.values}")


def _check_file_hint(value: str, mark: FileHint) -> None:
    if mark.extensions and not any(value.lower().endswith(e) for e in mark.extensions):
        raise SchemaValueError(
            f"not an accepted file type: {value!r}, "
            f"expected one of {mark.extensions}")


@dataclass(frozen=True, kw_only=True)
class Str(Shape):
    pytype: ClassVar[type] = str
    min: Min | None = None
    max: Max | None = None
    choices: Choices | None = None
    pattern: Pattern | None = None
    file_hint: FileHint | None = None
    is_password: IsPassword | None = None
    rows: Rows | None = None
    placeholder: Placeholder | None = None
    _extras: tuple[tuple[str, str], ...] = ()
    _compiled: re.Pattern[str] | None = field(
        default=None, init=False, repr=False, compare=False)

    @property
    def extras(self) -> dict[str, str]:
        return dict(self._extras)

    def __post_init__(self):
        name = type_name(self)

        check_opt(name, "min", self.min, Min)
        check_opt(name, "max", self.max, Max)
        check_opt(name, "choices", self.choices, Choices)
        check_opt(name, "pattern", self.pattern, Pattern)
        check_opt(name, "file_hint", self.file_hint, FileHint)
        check_opt(name, "is_password", self.is_password, IsPassword)
        check_opt(name, "rows", self.rows, Rows)
        check_opt(name, "placeholder", self.placeholder, Placeholder)
        object.__setattr__(self, "_extras", _normalize_extras(name, self._extras))

        if self.min is not None and type(self.min.value) is not int:
            raise TypeError(f"{name}.min: expected int, got {type(self.min.value).__name__}")

        if self.max is not None and type(self.max.value) is not int:
            raise TypeError(f"{name}.max: expected int, got {type(self.max.value).__name__}")

        if self.min is not None and self.min.exclusive:
            raise ValueError(f"{name}.min: exclusive bounds are not supported for lengths")

        if self.max is not None and self.max.exclusive:
            raise ValueError(f"{name}.max: exclusive bounds are not supported for lengths")

        if self.min is not None and cast(int, self.min.value) < 0:
            raise ValueError(f"{name}.min must be >= 0, got {render_number(self.min.value)}")

        if self.max is not None and cast(int, self.max.value) < 0:
            raise ValueError(f"{name}.max must be >= 0, got {render_number(self.max.value)}")

        if (self.min is not None and self.max is not None
                and cast(int, self.min.value) > cast(int, self.max.value)):
            raise ValueError(f"{name}: empty range ({render_number(self.min.value)}..{render_number(self.max.value)})")

        object.__setattr__(
            self, "_compiled",
            re.compile(self.pattern.value) if self.pattern is not None else None)

        if self.choices is not None:
            for c in self.choices.values:
                if type(c) is not str:
                    raise TypeError(f"{name}.choices: expected str, got {type(c).__name__}")

                if self.min is not None and len(c) < cast(int, self.min.value):
                    raise ValueError(f"{name}.choices: {c!r} shorter than minimum {render_number(self.min.value)}")

                if self.max is not None and len(c) > cast(int, self.max.value):
                    raise ValueError(f"{name}.choices: {c!r} longer than maximum {render_number(self.max.value)}")

                if self._compiled is not None and self._compiled.fullmatch(c) is None:
                    raise ValueError(f"{name}.choices: {c!r} does not match pattern")

                if self.file_hint is not None:
                    try:
                        _check_file_hint(c, self.file_hint)
                    except SchemaValueError as e:
                        raise ValueError(f"{name}.choices: {e.leaf}") from e

    def _check(self, value) -> None:
        if type(value) is not str:
            raise SchemaTypeError(f"expected str, got {type(value).__name__}")

        if self.min is not None and len(value) < cast(int, self.min.value):
            raise SchemaValueError(f"too short: {len(value)} chars, minimum {render_number(self.min.value)}")

        if self.max is not None and len(value) > cast(int, self.max.value):
            raise SchemaValueError(f"too long: {len(value)} chars, maximum {render_number(self.max.value)}")

        if self._compiled is not None and self._compiled.fullmatch(value) is None:
            pattern = cast(Pattern, self.pattern)
            if pattern.message is not None:
                raise SchemaValueError(pattern.message)
            raise SchemaValueError(f"does not match pattern {pattern.value!r}")

        if self.file_hint is not None:
            _check_file_hint(value, self.file_hint)

        if self.choices is not None and value not in self.choices.values:
            raise SchemaValueError(f"not a choice: {value!r}, expected one of {self.choices.values}")


@dataclass(frozen=True, kw_only=True)
class EnumShape(Shape):
    cls: type
    _extras: tuple[tuple[str, str], ...] = ()

    @property
    def pytype(self) -> type:  # type: ignore[override]
        return self.cls

    @property
    def extras(self) -> dict[str, str]:
        return dict(self._extras)

    def __post_init__(self):
        name = type_name(self)
        if not (isinstance(self.cls, type) and issubclass(self.cls, Enum)):
            raise TypeError(f"{name}.cls must be an Enum class, got {type(self.cls).__name__}")
        if issubclass(self.cls, Flag):
            raise TypeError(f"{name}.cls: Flag enums are not supported (OR-combinable, not a closed set)")
        if len(list(self.cls)) == 0:
            raise ValueError(f"{name}.cls: enum has no members")
        object.__setattr__(self, "_extras", _normalize_extras(name, self._extras))

    def _check(self, value) -> None:
        if type(value) is not self.cls:
            raise SchemaTypeError(f"expected {self.cls.__name__}, got {type(value).__name__}")


@dataclass(frozen=True, kw_only=True)
class Date(Shape):
    pytype: ClassVar[type] = date
    min: Min | None = None
    max: Max | None = None
    choices: Choices | None = None
    placeholder: Placeholder | None = None
    _extras: tuple[tuple[str, str], ...] = ()

    @property
    def extras(self) -> dict[str, str]:
        return dict(self._extras)

    def __post_init__(self):
        name = type_name(self)

        check_opt(name, "min", self.min, Min)
        check_opt(name, "max", self.max, Max)
        check_opt(name, "choices", self.choices, Choices)
        check_opt(name, "placeholder", self.placeholder, Placeholder)
        object.__setattr__(self, "_extras", _normalize_extras(name, self._extras))

        if self.min is not None and type(self.min.value) is not date:
            raise TypeError(f"{name}.min: expected date, got {type(self.min.value).__name__}")

        if self.max is not None and type(self.max.value) is not date:
            raise TypeError(f"{name}.max: expected date, got {type(self.max.value).__name__}")

        if self.min is not None and self.min.exclusive and self.min.value == date.max:
            raise ValueError(f"{name}: exclusive bound at {self.min.value} leaves no valid date")
        if self.max is not None and self.max.exclusive and self.max.value == date.min:
            raise ValueError(f"{name}: exclusive bound at {self.max.value} leaves no valid date")

        lo = None
        hi = None
        if self.min is not None:
            lo = self.min.value + timedelta(days=1) if self.min.exclusive else self.min.value
        if self.max is not None:
            hi = self.max.value - timedelta(days=1) if self.max.exclusive else self.max.value

        if lo is not None and hi is not None and lo > hi:
            raise ValueError(f"{name}: empty range ({render_number(self.min.value)}..{render_number(self.max.value)})")

        if self.choices is not None:
            for c in self.choices.values:
                if type(c) is not date:
                    raise TypeError(f"{name}.choices: expected date, got {type(c).__name__}")

                if lo is not None and c < lo:
                    raise ValueError(f"{name}.choices: {c} below minimum {self.min.value}")

                if hi is not None and c > hi:
                    raise ValueError(f"{name}.choices: {c} above maximum {self.max.value}")

    def _check(self, value) -> None:
        if type(value) is not date:
            raise SchemaTypeError(f"expected date, got {type(value).__name__}")

        if self.min is not None:
            minimum = cast(date, self.min.value)
            if self.min.exclusive:
                if value <= minimum:
                    raise SchemaValueError(f"too early: {value}, minimum {self.min.value} (exclusive)")
            elif value < minimum:
                raise SchemaValueError(f"too early: {value}, minimum {self.min.value}")

        if self.max is not None:
            maximum = cast(date, self.max.value)
            if self.max.exclusive:
                if value >= maximum:
                    raise SchemaValueError(f"too late: {value}, maximum {self.max.value} (exclusive)")
            elif value > maximum:
                raise SchemaValueError(f"too late: {value}, maximum {self.max.value}")

        if self.choices is not None and value not in self.choices.values:
            raise SchemaValueError(f"not a choice: {value}, expected one of {self.choices.values}")


@dataclass(frozen=True, kw_only=True)
class Time(Shape):
    pytype: ClassVar[type] = time
    min: Min | None = None
    max: Max | None = None
    choices: Choices | None = None
    placeholder: Placeholder | None = None
    _extras: tuple[tuple[str, str], ...] = ()

    @property
    def extras(self) -> dict[str, str]:
        return dict(self._extras)

    def __post_init__(self):
        name = type_name(self)

        check_opt(name, "min", self.min, Min)
        check_opt(name, "max", self.max, Max)
        check_opt(name, "choices", self.choices, Choices)
        check_opt(name, "placeholder", self.placeholder, Placeholder)
        object.__setattr__(self, "_extras", _normalize_extras(name, self._extras))

        if self.min is not None and type(self.min.value) is not time:
            raise TypeError(f"{name}.min: expected time, got {type(self.min.value).__name__}")

        if self.max is not None and type(self.max.value) is not time:
            raise TypeError(f"{name}.max: expected time, got {type(self.max.value).__name__}")

        if self.min is not None and self.min.value.tzinfo is not None:
            raise ValueError(f"{name}.min: must be naive (no tzinfo), got {self.min.value}")

        if self.max is not None and self.max.value.tzinfo is not None:
            raise ValueError(f"{name}.max: must be naive (no tzinfo), got {self.max.value}")

        if self.min is not None and self.min.value.microsecond != 0:
            raise ValueError(
                f"{name}.min: time precision is limited to whole seconds, got {self.min.value}")

        if self.max is not None and self.max.value.microsecond != 0:
            raise ValueError(
                f"{name}.max: time precision is limited to whole seconds, got {self.max.value}")

        if self.min is not None and self.min.exclusive and self.min.value == time(23, 59, 59):
            raise ValueError(f"{name}: exclusive bound at {self.min.value} leaves no valid time")
        if self.max is not None and self.max.exclusive and self.max.value == time.min:
            raise ValueError(f"{name}: exclusive bound at {self.max.value} leaves no valid time")

        if self.min is not None and self.max is not None:
            empty = self.min.value > self.max.value or (
                self.min.value == self.max.value
                and (self.min.exclusive or self.max.exclusive))
            if empty:
                raise ValueError(f"{name}: empty range ({render_number(self.min.value)}..{render_number(self.max.value)})")

        if self.choices is not None:
            for c in self.choices.values:
                if type(c) is not time:
                    raise TypeError(f"{name}.choices: expected time, got {type(c).__name__}")

                if c.tzinfo is not None:
                    raise ValueError(f"{name}.choices: must be naive (no tzinfo), got {c}")

                if c.microsecond != 0:
                    raise ValueError(
                        f"{name}.choices: time precision is limited to whole seconds, got {c}")

                if self.min is not None:
                    below = c <= self.min.value if self.min.exclusive else c < self.min.value
                    if below:
                        raise ValueError(f"{name}.choices: {c} below minimum {self.min.value}")

                if self.max is not None:
                    above = c >= self.max.value if self.max.exclusive else c > self.max.value
                    if above:
                        raise ValueError(f"{name}.choices: {c} above maximum {self.max.value}")

    def _check(self, value) -> None:
        if type(value) is not time:
            raise SchemaTypeError(f"expected time, got {type(value).__name__}")

        if value.tzinfo is not None:
            raise SchemaValueError(f"must be naive (no tzinfo): {value}")

        if value.microsecond != 0:
            raise SchemaValueError(f"time precision is limited to whole seconds: {value}")

        if self.min is not None:
            minimum = cast(time, self.min.value)
            if self.min.exclusive:
                if value <= minimum:
                    raise SchemaValueError(f"too early: {value}, minimum {self.min.value} (exclusive)")
            elif value < minimum:
                raise SchemaValueError(f"too early: {value}, minimum {self.min.value}")

        if self.max is not None:
            maximum = cast(time, self.max.value)
            if self.max.exclusive:
                if value >= maximum:
                    raise SchemaValueError(f"too late: {value}, maximum {self.max.value} (exclusive)")
            elif value > maximum:
                raise SchemaValueError(f"too late: {value}, maximum {self.max.value}")

        if self.choices is not None and value not in self.choices.values:
            raise SchemaValueError(f"not a choice: {value}, expected one of {self.choices.values}")


@dataclass(frozen=True, kw_only=True)
class Bool(Shape):
    pytype: ClassVar[type] = bool
    _extras: tuple[tuple[str, str], ...] = ()

    @property
    def extras(self) -> dict[str, str]:
        return dict(self._extras)

    def __post_init__(self):
        name = type_name(self)
        object.__setattr__(self, "_extras", _normalize_extras(name, self._extras))

    def _check(self, value) -> None:
        if type(value) is not bool:
            raise SchemaTypeError(f"expected bool, got {type(value).__name__}")


@dataclass(frozen=True, kw_only=True)
class NoneShape(Shape):
    pytype: ClassVar[type] = type(None)
    _extras: tuple[tuple[str, str], ...] = ()

    @property
    def extras(self) -> dict[str, str]:
        return dict(self._extras)

    def __post_init__(self):
        name = type_name(self)
        object.__setattr__(self, "_extras", _normalize_extras(name, self._extras))

    def _check(self, value) -> None:
        if value is not None:
            raise SchemaTypeError(f"expected None, got {type(value).__name__}")

    def option_id(self) -> str:
        return "None"


def _check_item_options(name: str, items) -> None:
    if type(items) is not tuple or not items or any(
            not isinstance(item, Shape) for item in items):
        raise TypeError(f"{name} must be a non-empty tuple of shapes")
    if duplicate_options(items):
        raise ValueError(f"{name} has duplicate option types")
    clashing = duplicate_discriminators(items)
    if clashing:
        raise ValueError(
            f"{name}: duplicate discriminator name(s): {', '.join(clashing)}")
    if len(items) == 1 and isinstance(items[0], NoneShape):
        raise TypeError(f"{name} cannot be NoneShape")


def _check_length_bounds(name: str, minimum, maximum) -> None:
    check_opt(name, "min", minimum, Min)
    check_opt(name, "max", maximum, Max)

    if minimum is not None and type(minimum.value) is not int:
        raise TypeError(f"{name}.min: expected int, got {type(minimum.value).__name__}")

    if maximum is not None and type(maximum.value) is not int:
        raise TypeError(f"{name}.max: expected int, got {type(maximum.value).__name__}")

    if minimum is not None and minimum.exclusive:
        raise ValueError(f"{name}.min: exclusive bounds are not supported for lengths")

    if maximum is not None and maximum.exclusive:
        raise ValueError(f"{name}.max: exclusive bounds are not supported for lengths")

    if minimum is not None and cast(int, minimum.value) < 0:
        raise ValueError(f"{name}.min must be >= 0, got {render_number(minimum.value)}")

    if maximum is not None and cast(int, maximum.value) < 0:
        raise ValueError(f"{name}.max must be >= 0, got {render_number(maximum.value)}")

    if (minimum is not None and maximum is not None
            and cast(int, minimum.value) > cast(int, maximum.value)):
        raise ValueError(f"{name}: empty range ({render_number(minimum.value)}..{render_number(maximum.value)})")


@dataclass(frozen=True, kw_only=True)
class List(Shape):
    pytype: ClassVar[type] = list
    item: tuple[Shape, ...]
    min: Min | None = None
    max: Max | None = None
    _extras: tuple[tuple[str, str], ...] = ()

    @property
    def extras(self) -> dict[str, str]:
        return dict(self._extras)

    def __post_init__(self):
        name = type_name(self)

        _check_item_options(f"{name}.item", self.item)
        _check_length_bounds(name, self.min, self.max)
        object.__setattr__(self, "_extras", _normalize_extras(name, self._extras))

    def _item_at(self, index: int) -> tuple[Shape, ...]:
        return self.item

    def option_id(self) -> str:
        return f"list[{' | '.join(item.option_id() for item in self.item)}]"

    def _check(self, value) -> None:
        self._check_length(value)
        for i, item in enumerate(value):
            try:
                check_options_value(self.item, item)
            except (TypeError, ValueError) as e:
                raise _prefixed(e, (i,)) from e

    def _validate_data(self, value) -> None:
        self._check_length(value)

    def _check_length(self, value) -> None:
        _check_sequence_length(self, value)


def _check_sequence_length(shape, value) -> None:
    if type(value) is not shape.pytype:
        raise SchemaTypeError(f"expected {shape.pytype.__name__}, got {type(value).__name__}")

    if shape.min is not None and len(value) < cast(int, shape.min.value):
        raise SchemaValueError(f"too few items: {len(value)}, minimum {render_number(shape.min.value)}")

    if shape.max is not None and len(value) > cast(int, shape.max.value):
        raise SchemaValueError(f"too many items: {len(value)}, maximum {render_number(shape.max.value)}")


@dataclass(frozen=True, kw_only=True)
class Tuple(Shape):
    pytype: ClassVar[type] = tuple
    items: tuple[tuple[Shape, ...], ...]
    variadic: bool = False
    min: Min | None = None
    max: Max | None = None
    _extras: tuple[tuple[str, str], ...] = ()

    @property
    def extras(self) -> dict[str, str]:
        return dict(self._extras)

    def __post_init__(self):
        name = type_name(self)
        if type(self.items) is not tuple:
            raise TypeError(f"{name}.items must be a tuple of option tuples")
        if type(self.variadic) is not bool:
            raise TypeError(f"{name}.variadic must be bool")
        if self.variadic and len(self.items) != 1:
            raise ValueError(f"{name}: variadic tuples require exactly one item slot")
        for i, options in enumerate(self.items):
            _check_item_options(f"{name}.items[{i}]", options)
        _check_length_bounds(name, self.min, self.max)
        object.__setattr__(self, "_extras", _normalize_extras(name, self._extras))
        if not self.variadic:
            if ((self.min is not None and len(self.items) < cast(int, self.min.value))
                    or (self.max is not None and len(self.items) > cast(int, self.max.value))):
                raise ValueError(f"{name}: length bounds exclude fixed size {len(self.items)}")

    def option_id(self) -> str:
        slots = [" | ".join(s.option_id() for s in options) for options in self.items]
        content = ", ".join(slots)
        if self.variadic:
            content += ", ..."
        return f"tuple[{content if self.items else '()'}]"

    def _item_at(self, index: int) -> tuple[Shape, ...]:
        # Preserve extra positions for validation to report, never truncate them.
        if self.variadic:
            return self.items[0]
        return self.items[index] if index < len(self.items) else ()

    def _validate_data(self, value) -> None:
        _check_sequence_length(self, value)
        if not self.variadic and len(value) != len(self.items):
            raise SchemaValueError(f"expected {len(self.items)} items, got {len(value)}")

    def _check(self, value) -> None:
        self._validate_data(value)
        for i, item in enumerate(value):
            try:
                check_options_value(self._item_at(i), item)
            except (TypeError, ValueError) as e:
                raise _prefixed(e, (i,)) from e

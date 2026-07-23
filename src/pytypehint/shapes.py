import math
import re
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from enum import Enum, Flag
from typing import ClassVar, cast

from pytypehint.atoms import (
    Choices, Min, Max, MultipleOf, Pattern, IsPassword, IsPathFile, Rows,
    Step, Slider, Placeholder,
)
from pytypehint.errors import SchemaTypeError, SchemaValueError, _prefixed
from pytypehint.utils import check_opt, type_name
from pytypehint.validation import check_options_value


# Extras are stored as a sorted tuple of pairs, never as a dict: the shapes are
# frozen dataclasses with eq, so a dict field would break the generated __hash__
# at call time and stay mutable inside a value that advertises itself as frozen.
# Sorting makes equality independent of the order the atoms were written in; the
# `extras` property rebuilds the dict callers want on access.
def _normalize_extras(owner: str, value) -> tuple[tuple[str, str], ...]:
    if type(value) is not tuple:
        raise TypeError(f"{owner}._extras must be tuple, got {type(value).__name__}")

    for pair in value:
        if (type(pair) is not tuple or len(pair) != 2
                or any(type(s) is not str for s in pair)):
            raise TypeError(f"{owner}._extras: expected a (key, value) pair of str, got {pair!r}")

    # Compilation merges by key, so a repeat can only arrive from hand
    # construction — where it is not a layering to resolve but a broken mapping.
    keys = [k for k, _ in value]
    if len(set(keys)) != len(keys):
        raise ValueError(f"{owner}._extras must not repeat keys")

    return tuple(sorted(value))


class Shape:
    pytype: ClassVar[type]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "pytype"):
            raise TypeError(f"{cls.__name__} must declare pytype")

    def _check(self, value) -> None:
        raise NotImplementedError(f"{type(self).__name__} must implement check")

    # Stable, readable name for this option. Routing uses the runtime type;
    # when two options share one, this is what tells them apart — as the value
    # of "$type" in the discriminated wrapper and in the messages that offer it.
    # Scalars are their type name, dataclasses and enums their class name, and
    # a list spells out its items: list[str], list[int], list[list[str]].
    def option_id(self) -> str:
        return self.pytype.__name__


# Two options are routable when their runtime types differ; when they coincide,
# their identities must differ so a discriminator can name one of them. This keys
# on runtime type alone: two enums that share a class name have different runtime
# types and route by their exact member type, so they are not duplicates here. A
# separate rule (structure._check_discriminators) still rejects that name clash as
# a public-identity collision — that concern is the field's, not this function's.
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
            raise ValueError(f"{name}: empty range ({self.min.value}..{self.max.value})")

        if self.choices is not None:
            for c in self.choices.values:
                if type(c) is not int:
                    raise TypeError(f"{name}.choices: expected int, got {type(c).__name__}")

                if lo is not None and c < lo:
                    raise ValueError(f"{name}.choices: {c} below minimum {self.min.value}")

                if hi is not None and c > hi:
                    raise ValueError(f"{name}.choices: {c} above maximum {self.max.value}")

        if self.multiple_of is not None:
            m = self.multiple_of.value

            if self.choices is not None:
                for c in self.choices.values:
                    if c % m != 0:
                        raise ValueError(f"{name}.choices: {c} is not a multiple of {m}")

            if lo is not None and hi is not None:
                smallest = -(-lo // m) * m
                if smallest > hi:
                    raise ValueError(
                        f"{name}: no multiple of {m} in range ({self.min.value}..{self.max.value})")

        if self.slider is not None and (self.min is None or self.max is None):
            raise ValueError(f"{name}: slider requires min and max")

    def _check(self, value) -> None:
        if type(value) is not int:
            raise SchemaTypeError(f"expected int, got {type(value).__name__}")

        if self.min is not None:
            minimum = cast(int, self.min.value)
            if self.min.exclusive:
                if value <= minimum:
                    raise SchemaValueError(f"too small: {value}, minimum {self.min.value} (exclusive)")
            elif value < minimum:
                raise SchemaValueError(f"too small: {value}, minimum {self.min.value}")

        if self.max is not None:
            maximum = cast(int, self.max.value)
            if self.max.exclusive:
                if value >= maximum:
                    raise SchemaValueError(f"too large: {value}, maximum {self.max.value} (exclusive)")
            elif value > maximum:
                raise SchemaValueError(f"too large: {value}, maximum {self.max.value}")

        if self.multiple_of is not None and value % self.multiple_of.value != 0:
            raise SchemaValueError(f"not a multiple of {self.multiple_of.value}: {value}")

        if self.choices is not None and value not in self.choices.values:
            raise SchemaValueError(f"not a choice: {value}, expected one of {self.choices.values}")


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

        if self.min is not None and not math.isfinite(self.min.value):
            raise ValueError(f"{name}.min: must be finite, got {self.min.value}")

        if self.max is not None and not math.isfinite(self.max.value):
            raise ValueError(f"{name}.max: must be finite, got {self.max.value}")

        if self.min is not None and self.max is not None:
            empty = self.min.value > self.max.value or (
                self.min.value == self.max.value
                and (self.min.exclusive or self.max.exclusive))
            if empty:
                raise ValueError(f"{name}: empty range ({self.min.value}..{self.max.value})")

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


@dataclass(frozen=True, kw_only=True)
class Str(Shape):
    pytype: ClassVar[type] = str
    min: Min | None = None
    max: Max | None = None
    choices: Choices | None = None
    pattern: Pattern | None = None
    is_path_file: IsPathFile | None = None
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
        check_opt(name, "is_path_file", self.is_path_file, IsPathFile)
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
            raise ValueError(f"{name}.min must be >= 0, got {self.min.value}")

        if self.max is not None and cast(int, self.max.value) < 0:
            raise ValueError(f"{name}.max must be >= 0, got {self.max.value}")

        if (self.min is not None and self.max is not None
                and cast(int, self.min.value) > cast(int, self.max.value)):
            raise ValueError(f"{name}: empty range ({self.min.value}..{self.max.value})")

        # Equality uses the pattern string, not the compiled regex object.
        object.__setattr__(
            self, "_compiled",
            re.compile(self.pattern.value) if self.pattern is not None else None)

        if self.choices is not None:
            for c in self.choices.values:
                if type(c) is not str:
                    raise TypeError(f"{name}.choices: expected str, got {type(c).__name__}")

                if self.min is not None and len(c) < cast(int, self.min.value):
                    raise ValueError(f"{name}.choices: {c!r} shorter than minimum {self.min.value}")

                if self.max is not None and len(c) > cast(int, self.max.value):
                    raise ValueError(f"{name}.choices: {c!r} longer than maximum {self.max.value}")

                if self._compiled is not None and self._compiled.fullmatch(c) is None:
                    raise ValueError(f"{name}.choices: {c!r} does not match pattern")

                if self.is_path_file is not None and self.is_path_file.extensions:
                    if not any(c.lower().endswith(e) for e in self.is_path_file.extensions):
                        raise ValueError(f"{name}.choices: {c!r} is not an accepted file type")

    def _check(self, value) -> None:
        if type(value) is not str:
            raise SchemaTypeError(f"expected str, got {type(value).__name__}")

        if self.min is not None and len(value) < cast(int, self.min.value):
            raise SchemaValueError(f"too short: {len(value)} chars, minimum {self.min.value}")

        if self.max is not None and len(value) > cast(int, self.max.value):
            raise SchemaValueError(f"too long: {len(value)} chars, maximum {self.max.value}")

        if self._compiled is not None and self._compiled.fullmatch(value) is None:
            pattern = cast(Pattern, self.pattern)
            if pattern.message is not None:
                raise SchemaValueError(pattern.message)
            raise SchemaValueError(f"does not match pattern {pattern.value!r}")

        if self.is_path_file is not None and self.is_path_file.extensions:
            if not any(value.lower().endswith(e) for e in self.is_path_file.extensions):
                raise SchemaValueError(
                    f"not an accepted file type: {value!r}, "
                    f"expected one of {self.is_path_file.extensions}")

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

        # An exclusive bound at the calendar's edge would overflow the timedelta
        # arithmetic below; there is also no valid date beyond it.
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
            raise ValueError(f"{name}: empty range ({self.min.value}..{self.max.value})")

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

        # An exclusive bound at the clock's edge admits no time: there is no naive
        # time before 00:00:00 or after 23:59:59.999999. Symmetric with Date.
        if self.min is not None and self.min.exclusive and self.min.value == time.max:
            raise ValueError(f"{name}: exclusive bound at {self.min.value} leaves no valid time")
        if self.max is not None and self.max.exclusive and self.max.value == time.min:
            raise ValueError(f"{name}: exclusive bound at {self.max.value} leaves no valid time")

        if self.min is not None and self.max is not None:
            empty = self.min.value > self.max.value or (
                self.min.value == self.max.value
                and (self.min.exclusive or self.max.exclusive))
            if empty:
                raise ValueError(f"{name}: empty range ({self.min.value}..{self.max.value})")

        if self.choices is not None:
            for c in self.choices.values:
                if type(c) is not time:
                    raise TypeError(f"{name}.choices: expected time, got {type(c).__name__}")

                if c.tzinfo is not None:
                    raise ValueError(f"{name}.choices: must be naive (no tzinfo), got {c}")

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

        if type(self.item) is not tuple or not self.item or any(
                not isinstance(item, Shape) for item in self.item):
            raise TypeError(f"{name}.item must be a non-empty tuple of shapes")
        if duplicate_options(self.item):
            raise ValueError(f"{name}.item has duplicate option types")
        if len(self.item) == 1 and isinstance(self.item[0], NoneShape):
            raise TypeError(f"{name}.item cannot be NoneShape")

        check_opt(name, "min", self.min, Min)
        check_opt(name, "max", self.max, Max)
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
            raise ValueError(f"{name}.min must be >= 0, got {self.min.value}")

        if self.max is not None and cast(int, self.max.value) < 0:
            raise ValueError(f"{name}.max must be >= 0, got {self.max.value}")

        if (self.min is not None and self.max is not None
                and cast(int, self.min.value) > cast(int, self.max.value)):
            raise ValueError(f"{name}: empty range ({self.min.value}..{self.max.value})")

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
        if type(value) is not list:
            raise SchemaTypeError(f"expected list, got {type(value).__name__}")

        if self.min is not None and len(value) < cast(int, self.min.value):
            raise SchemaValueError(f"too few items: {len(value)}, minimum {self.min.value}")

        if self.max is not None and len(value) > cast(int, self.max.value):
            raise SchemaValueError(f"too many items: {len(value)}, maximum {self.max.value}")

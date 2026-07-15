class _MissingType:
    def __repr__(self):
        return "MISSING"

    # Sentinel: pickle/copy must round-trip to the one instance, not a clone.
    # Returning the global's name makes both resolve back to this singleton.
    def __reduce__(self):
        return "MISSING"


MISSING = _MissingType()


def type_name(obj) -> str:
    return type(obj).__name__


def check_opt(owner: str, attr: str, value, expected: type) -> None:
    if value is not None and type(value) is not expected:
        raise TypeError(f"{owner}.{attr} must be {expected.__name__}, got {type(value).__name__}")

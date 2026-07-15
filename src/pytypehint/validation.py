from pytypehint.errors import SchemaTypeError


def check_options_value(shapes, value) -> None:
    for shape in shapes:
        if type(value) is shape.pytype:
            shape._check(value)
            return
    accepted = " | ".join(shape.pytype.__name__ for shape in shapes)
    raise SchemaTypeError(f"expected {accepted}, got {type(value).__name__}")

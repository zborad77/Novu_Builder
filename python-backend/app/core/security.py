"""
Password strength validation and shared security helpers.
"""
import re

# Requirements for all user-facing passwords
_PASSWORD_MIN_LEN = 10
_PASSWORD_RULES: list[tuple[str, str]] = [
    (r"[A-Z]", "alespoň jedno velké písmeno"),
    (r"[a-z]", "alespoň jedno malé písmeno"),
    (r"[0-9]", "alespoň jednu cifru"),
    (r"[^A-Za-z0-9]", "alespoň jeden speciální znak (!@#$%^&*…)"),
]


def validate_password_strength(password: str) -> list[str]:
    """Return list of human-readable error strings. Empty list = password OK."""
    errors: list[str] = []
    if len(password) < _PASSWORD_MIN_LEN:
        errors.append(f"Heslo musí mít alespoň {_PASSWORD_MIN_LEN} znaků.")
    for pattern, description in _PASSWORD_RULES:
        if not re.search(pattern, password):
            errors.append(f"Heslo musí obsahovat {description}.")
    return errors


def enforce_password_strength(password: str) -> None:
    """Raise ValueError with a combined message if password is too weak."""
    errors = validate_password_strength(password)
    if errors:
        raise ValueError(" ".join(errors))

"""Shared LIKE/ILIKE escaping helpers.

Reuses the project search hardening pattern so user input containing LIKE
metacharacters is always treated literally unless the caller adds wildcards
explicitly around the escaped term.
"""

LIKE_ESCAPE_CHAR = "\\"


def build_contains_ilike_pattern(value: str) -> str:
    escaped = (
        value
        .replace(LIKE_ESCAPE_CHAR, LIKE_ESCAPE_CHAR * 2)
        .replace("%", LIKE_ESCAPE_CHAR + "%")
        .replace("_", LIKE_ESCAPE_CHAR + "_")
    )
    return f"%{escaped}%"

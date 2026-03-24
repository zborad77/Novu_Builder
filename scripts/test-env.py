"""
Environment variable check — existence only, no value validation.

Required:
    DATABASE_URL
    JWT_SECRET

Optional (checked but not required):
    REDIS_URL
    STORAGE_ROOT
    APP_ENV

Usage:
    python scripts/test-env.py
"""

import os
import sys

REQUIRED = [
    "DATABASE_URL",
    "JWT_SECRET",
]

OPTIONAL = [
    "REDIS_URL",
    "STORAGE_ROOT",
    "APP_ENV",
]


def main() -> None:
    missing = []

    for var in REQUIRED:
        if os.environ.get(var):
            print(f"OK       {var}")
        else:
            print(f"MISSING  {var}")
            missing.append(var)

    for var in OPTIONAL:
        if os.environ.get(var):
            print(f"OK       {var}")
        else:
            print(f"SKIP     {var}  (optional)")

    if missing:
        print(f"\nFAIL: missing required variables: {', '.join(missing)}")
        sys.exit(1)

    print("\nOK")


if __name__ == "__main__":
    main()

"""Titik masuk Creator Toolkit."""

from __future__ import annotations

import sys

from app.constants import APP_NAME, APP_TAGLINE, APP_VERSION, MIN_PYTHON


def main(argv: list[str]) -> int:
    if sys.version_info < MIN_PYTHON:
        needed = ".".join(str(part) for part in MIN_PYTHON)
        print(f"{APP_NAME} membutuhkan Python {needed} atau lebih baru.", file=sys.stderr)
        return 1

    if "--version" in argv:
        print(f"{APP_NAME} {APP_VERSION} - {APP_TAGLINE}")
        return 0

    if "--check" in argv:
        from app.diagnostics import format_report

        print(format_report())
        return 0

    from app.application import run

    return run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

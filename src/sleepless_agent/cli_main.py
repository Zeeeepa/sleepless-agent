"""Backward-compatible CLI entry for older installer scripts."""

from __future__ import annotations

import sys
from typing import Sequence

from sleepless_agent.__main__ import main as _main


def main(argv: Sequence[str] | None = None) -> int:
    """Delegate to the unified __main__ entry point."""
    args = list(argv) if argv is not None else sys.argv[1:]
    return _main(args)

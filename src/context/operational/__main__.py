"""Entry point for ``python -m src.context.operational``."""

from __future__ import annotations

import sys

from src.context.operational.run_operational_context import main

if __name__ == "__main__":
    sys.exit(main())

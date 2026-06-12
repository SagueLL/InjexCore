"""Entry point for ``python -m src.context.bom``.

The BOM component is currently the only external-context source, so this
forwards straight to its CLI. When a second context source exists, promote
the ``src/intelligence/__main__.py`` dispatcher pattern to ``src/context``.
"""

from __future__ import annotations

import sys

from src.context.bom.run_bom_context import main

if __name__ == "__main__":
    sys.exit(main())

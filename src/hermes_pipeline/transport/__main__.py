"""``python -m hermes_pipeline.transport`` entry (keep-marked fake runtime).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE
"""

from __future__ import annotations

import sys

from ._main import main

if __name__ == "__main__":
    sys.exit(main())

"""packages/ui/scripts holds plain files, not a package: put the folder on the import path."""

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

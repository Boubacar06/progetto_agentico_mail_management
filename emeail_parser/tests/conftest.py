import sys, os
from pathlib import Path
ROOT = Path(__file__).parent.parent
SRC = ROOT / 'src'
if SRC.exists():
    sys.path.append(str(SRC))

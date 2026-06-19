import sys
from pathlib import Path

# Make project source importable from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from echosense.guardian import validate_guardian_configuration  # noqa: E402

if __name__ == "__main__":
    validate_guardian_configuration()

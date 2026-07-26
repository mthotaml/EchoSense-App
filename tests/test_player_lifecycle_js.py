import subprocess
from pathlib import Path


def test_browser_player_lifecycle_permutations() -> None:
    result = subprocess.run(
        ["node", "tests/player_lifecycle.test.js"],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr

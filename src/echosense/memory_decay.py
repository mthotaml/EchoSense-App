from __future__ import annotations

import os

from echosense.memory import memory_from_environment


def main() -> None:
    half_life_days = float(os.getenv("ECHOSENSE_PREFERENCE_HALF_LIFE_DAYS", "30"))
    epsilon = float(os.getenv("ECHOSENSE_PREFERENCE_DECAY_EPSILON", "0.001"))
    changed = memory_from_environment().decay_preferences(
        half_life_days=half_life_days,
        epsilon=epsilon,
    )
    print(f"decayed_preferences={changed}")


if __name__ == "__main__":
    main()

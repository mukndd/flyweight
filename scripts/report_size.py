"""Print project disk usage by category. Read-only; touches only this project tree."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {
    "Source (apps/packages/services/scripts/docs)": ["apps", "packages", "services", "scripts", "docs"],
    "node_modules": ["node_modules"],
    "Python virtual environment (.venv)": [".venv"],
    "Raw data": ["data/raw"],
    "Processed data": ["data/processed"],
    "Checkpoints": ["checkpoints"],
    "Replays": ["replays"],
    "Build output (dist)": ["dist"],
}


def size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total


def human(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def main():
    grand_total = 0
    for label, paths in CATEGORIES.items():
        total = sum(size(ROOT / p) for p in paths)
        grand_total += total
        print(f"{label:45s} {human(total):>12s}")
    print(f"{'Total':45s} {human(grand_total):>12s}")


if __name__ == "__main__":
    main()

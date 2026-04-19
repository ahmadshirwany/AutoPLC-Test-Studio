from __future__ import annotations

from datetime import datetime
from pathlib import Path


def create_output_folder(output_root: Path, purpose_slug: str) -> tuple[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_folder_name = f"{purpose_slug}-{timestamp}"
    candidate = output_root / base_folder_name

    suffix = 1
    while candidate.exists():
        candidate = output_root / f"{base_folder_name}-{suffix}"
        suffix += 1

    candidate.mkdir(parents=True, exist_ok=False)
    return candidate.name, candidate

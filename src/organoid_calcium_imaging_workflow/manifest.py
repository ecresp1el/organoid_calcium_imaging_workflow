"""Portable, validated recording manifest used by every workflow stage."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class RecordingManifest:
    recording_name: str
    ims_path: str
    raw_tiff: str
    motion_corrected_tiff: str
    max_projection: str
    average_projection: str
    std_projection: str
    roi_labels: str | None = None

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")

    @classmethod
    def read(cls, path: Path) -> "RecordingManifest":
        return cls(**json.loads(path.read_text()))

    def required_paths(self) -> dict[str, Path]:
        return {
            "raw_tiff": Path(self.raw_tiff),
            "motion_corrected_tiff": Path(self.motion_corrected_tiff),
            "max_projection": Path(self.max_projection),
            "average_projection": Path(self.average_projection),
            "std_projection": Path(self.std_projection),
        }

    def validate_preprocessing(self) -> list[str]:
        return [name for name, value in self.required_paths().items() if not value.is_file()]

"""
Configuration management for CodeMorph.

Reads from .env files, environment variables, and CLI overrides.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class MigrationConfig:
    """Central configuration for a migration run."""

    # Source / target
    source_lang: str = "python"
    target_lang: str = "typescript"
    source_dir: Path = field(default_factory=lambda: Path("."))
    output_dir: Optional[Path] = None

    # Feature flags
    dry_run: bool = False
    preserve_comments: bool = True
    generate_types: bool = True
    run_validators: bool = True
    parallel: bool = False
    max_workers: int = 4

    # Paths
    rules_file: Optional[Path] = None
    ignore_file: Optional[Path] = None

    # Logging
    verbose: bool = False
    log_file: Optional[Path] = None

    # Advanced
    custom_patterns: List[str] = field(default_factory=list)
    env_vars: Dict[str, str] = field(default_factory=dict)

    # ---- helpers ----------------------------------------------------------

    def resolve_paths(self) -> None:
        """Resolve relative paths to absolute."""
        self.source_dir = Path(self.source_dir).resolve()
        if self.output_dir:
            self.output_dir = Path(self.output_dir).resolve()
        else:
            self.output_dir = self.source_dir.parent / f"{self.source_dir.name}_migrated"

    @classmethod
    def from_env(cls, prefix: str = "CODEMORPH_") -> "MigrationConfig":
        """Build config from environment variables."""
        kwargs: dict = {}
        mapping = {
            f"{prefix}SOURCE_LANG": ("source_lang", str),
            f"{prefix}TARGET_LANG": ("target_lang", str),
            f"{prefix}SOURCE_DIR": ("source_dir", Path),
            f"{prefix}OUTPUT_DIR": ("output_dir", Path),
            f"{prefix}DRY_RUN": ("dry_run", lambda v: v.lower() in ("1", "true", "yes")),
            f"{prefix}VERBOSE": ("verbose", lambda v: v.lower() in ("1", "true", "yes")),
            f"{prefix}MAX_WORKERS": ("max_workers", int),
        }
        for env_key, (attr, converter) in mapping.items():
            val = os.environ.get(env_key)
            if val is not None:
                kwargs[attr] = converter(val)
        return cls(**kwargs)

    @classmethod
    def from_dict(cls, data: dict) -> "MigrationConfig":
        """Build config from a plain dict (e.g. parsed YAML/JSON)."""
        # convert string paths
        for key in ("source_dir", "output_dir", "rules_file", "ignore_file", "log_file"):
            if key in data and data[key] is not None:
                data[key] = Path(data[key])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        """Serialize to a plain dict for logging / JSON export."""
        result = {}
        for key in self.__dataclass_fields__:
            val = getattr(self, key)
            if isinstance(val, Path):
                val = str(val)
            result[key] = val
        return result


# ---------------------------------------------------------------------------
# Defaults / presets
# ---------------------------------------------------------------------------

PRESETS: Dict[str, Dict] = {
    "python-to-typescript": {
        "source_lang": "python",
        "target_lang": "typescript",
        "generate_types": True,
    },
    "python-to-javascript": {
        "source_lang": "python",
        "target_lang": "javascript",
        "generate_types": False,
    },
    "javascript-to-typescript": {
        "source_lang": "javascript",
        "target_lang": "typescript",
        "generate_types": True,
    },
    "flask-to-fastapi": {
        "source_lang": "python",
        "target_lang": "python",
        "custom_patterns": ["flask_to_fastapi"],
    },
}


def load_preset(name: str) -> MigrationConfig:
    """Return a MigrationConfig pre-filled from a named preset."""
    if name not in PRESETS:
        raise ValueError(f"Unknown preset {name!r}. Choose from: {list(PRESETS)}")
    return MigrationConfig(**PRESETS[name])

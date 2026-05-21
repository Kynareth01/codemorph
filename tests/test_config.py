"""Tests for the migration config."""

from pathlib import Path

import pytest

from codemorph.config import MigrationConfig, PRESETS, load_preset


class TestMigrationConfig:
    def test_defaults(self):
        config = MigrationConfig()
        assert config.source_lang == "python"
        assert config.target_lang == "typescript"
        assert config.dry_run is False

    def test_from_dict(self):
        data = {
            "source_lang": "python",
            "target_lang": "javascript",
            "dry_run": True,
        }
        config = MigrationConfig.from_dict(data)
        assert config.source_lang == "python"
        assert config.target_lang == "javascript"
        assert config.dry_run is True

    def test_resolve_paths(self):
        config = MigrationConfig(source_dir=Path("."))
        config.resolve_paths()
        assert config.source_dir.is_absolute()
        assert config.output_dir is not None
        assert config.output_dir.is_absolute()

    def test_to_dict(self):
        config = MigrationConfig()
        data = config.to_dict()
        assert isinstance(data, dict)
        assert "source_lang" in data
        assert "target_lang" in data

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("CODEMORPH_SOURCE_LANG", "python")
        monkeypatch.setenv("CODEMORPH_TARGET_LANG", "javascript")
        monkeypatch.setenv("CODEMORPH_DRY_RUN", "true")
        config = MigrationConfig.from_env()
        assert config.source_lang == "python"
        assert config.target_lang == "javascript"
        assert config.dry_run is True


class TestPresets:
    def test_python_to_typescript(self):
        config = load_preset("python-to-typescript")
        assert config.source_lang == "python"
        assert config.target_lang == "typescript"
        assert config.generate_types is True

    def test_python_to_javascript(self):
        config = load_preset("python-to-javascript")
        assert config.target_lang == "javascript"
        assert config.generate_types is False

    def test_unknown_preset(self):
        with pytest.raises(ValueError, match="Unknown preset"):
            load_preset("nonexistent")

    def test_all_presets_valid(self):
        for name in PRESETS:
            config = load_preset(name)
            assert config.source_lang in ("python", "javascript", "typescript")

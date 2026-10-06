"""scripts/bump_extension_version.py updates every version, and only those."""

import importlib.util
import json
import shutil
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "bump_extension_version", ROOT / "scripts" / "bump_extension_version.py"
)
bump_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bump_module)

FILES = ["extension/manifest.json", "extension/.claude-plugin/plugin.json",
         "extension/pyproject.toml", "extension/src/scout_mcp/__init__.py"]


@pytest.fixture
def copy(tmp_path):
    for f in FILES:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / f, tmp_path / f)
    (tmp_path / "extension/CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n\n- X.\n")
    return tmp_path


def test_bump_sets_every_version(copy):
    changed = bump_module.bump(copy, "9.8.7", today=date(2026, 10, 7))
    assert len(changed) == 5
    assert json.loads((copy / FILES[0]).read_text())["version"] == "9.8.7"
    assert json.loads((copy / FILES[1]).read_text())["version"] == "9.8.7"
    assert 'version = "9.8.7"' in (copy / FILES[2]).read_text()
    assert '__version__ = "9.8.7"' in (copy / FILES[3]).read_text()
    # Only the package's own version line, not dependency pins or tool settings.
    original = (ROOT / FILES[2]).read_text()
    assert (copy / FILES[2]).read_text().count("9.8.7") == 1
    assert len((copy / FILES[2]).read_text()) - len(original) == len("9.8.7") - len(
        original.split('version = "')[1].split('"')[0])


def test_rejects_non_versions(copy):
    with pytest.raises(ValueError):
        bump_module.bump(copy, "v1.0")


def test_unreleased_changes_become_the_release_notes(copy):
    log = copy / "extension/CHANGELOG.md"
    log.write_text("# Changelog\n\n## Unreleased\n\n- New thing.\n\n## 0.1.0 (2026-01-01)\n")
    bump_module.bump(copy, "0.2.0", today=date(2026, 10, 7))
    assert "## 0.2.0 (2026-10-07)\n\n- New thing." in log.read_text()
    # Running it again for the same version leaves the CHANGELOG alone.
    assert log not in bump_module.bump(copy, "0.2.0")


def test_a_release_needs_release_notes(copy):
    (copy / "extension/CHANGELOG.md").write_text("# Changelog\n\n## 0.1.0 (2026-01-01)\n")
    with pytest.raises(RuntimeError, match="Unreleased"):
        bump_module.bump(copy, "0.2.0")

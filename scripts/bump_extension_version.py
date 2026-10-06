"""Set the Scout extension's version everywhere it is recorded.

    uv run python scripts/bump_extension_version.py 0.3.0

Updates the Claude Desktop manifest, the Claude Code plugin manifest, the
package metadata and ``__version__``, turns the CHANGELOG's "Unreleased"
section into this version's, then refreshes both lock files. The release
workflow publishes whatever version these say, with that CHANGELOG section as
its notes, and extension/tests/test_packaging.py fails if they ever disagree.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def bump(root: Path, version: str, today: date | None = None) -> list[Path]:
    """Write ``version`` into every place it is recorded; return the files changed."""
    if not SEMVER.match(version):
        raise ValueError(f"Not a version like 1.2.3: {version!r}")
    ext = root / "extension"
    changed = []

    for manifest in (ext / "manifest.json", ext / ".claude-plugin" / "plugin.json"):
        data = json.loads(manifest.read_text())
        data["version"] = version
        manifest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        changed.append(manifest)

    for path, pattern, replacement in (
        (ext / "pyproject.toml", r'(?m)^version = "[^"]+"', f'version = "{version}"'),
        (ext / "src" / "scout_mcp" / "__init__.py", r'__version__ = "[^"]+"',
         f'__version__ = "{version}"'),
    ):
        text, n = re.subn(pattern, replacement, path.read_text(), count=1)
        if n != 1:
            raise RuntimeError(f"No version found in {path}")
        path.write_text(text)
        changed.append(path)

    changelog = ext / "CHANGELOG.md"
    text = changelog.read_text()
    if f"\n## {version} " not in text:
        day = (today or date.today()).isoformat()
        text, n = re.subn(r"(?m)^## Unreleased$", f"## {version} ({day})", text, count=1)
        if n != 1:
            raise RuntimeError(f"{changelog} has no '## Unreleased' section for {version}")
        changelog.write_text(text)
        changed.append(changelog)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("version", help="new version, e.g. 0.3.0")
    parser.add_argument("--no-lock", action="store_true", help="skip refreshing lock files")
    args = parser.parse_args()

    for path in bump(ROOT, args.version):
        print(f"updated {path.relative_to(ROOT)}")
    if not args.no_lock:
        for directory in (ROOT / "extension", ROOT):
            subprocess.run(["uv", "lock"], cwd=directory, check=True)
    print(f"Check the {args.version} section of extension/CHANGELOG.md: it is the release notes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

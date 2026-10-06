"""Extension settings, read from the environment.

Scout needs no API keys. The install form asks where to keep the notebook
and, optionally, for a GitHub token (SCOUT_GITHUB_TOKEN), which raises GitHub's
search limit from 10 to 30 a minute for people who research many companies at
once. Scout never reads credentials the user set in their environment for
other tools: only the token they gave Scout itself.

A blank optional field can arrive as an empty string or, in some hosts, as the
unsubstituted ``${user_config.x}`` placeholder; both mean unset.
"""

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    if not value or value.startswith("${"):
        return None
    return value


@dataclass(frozen=True)
class Config:
    data_dir: Path
    github_token: str | None = None

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            data_dir=Path(_env("SCOUT_DATA_DIR") or Path.home() / ".scout").expanduser(),
            github_token=_env("SCOUT_GITHUB_TOKEN"),
        )

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = REPO_ROOT / "configs" / "config.yaml"
_ENV = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand(v: Any) -> Any:
    if isinstance(v, str):
        return _ENV.sub(lambda m: os.environ.get(m.group(1), ""), v)
    if isinstance(v, dict):
        return {k: _expand(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_expand(x) for x in v]
    return v


class Config(dict):
    """Plain dict with attribute access for the top-level sections.

    Relative paths in the config resolve against the project root, taken to be
    the parent of the configs/ directory. That holds both in a checkout and in
    the container (/app/configs/config.yaml -> /app).
    """

    root: Path = REPO_ROOT

    def __getattr__(self, item: str) -> Any:
        try:
            return self[item]
        except KeyError as e:
            raise AttributeError(item) from e

    def path(self, value: str) -> Path:
        """Resolve a path from the config relative to the repo root."""
        p = Path(value)
        return p if p.is_absolute() else self.root / p


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _read(path: Path) -> dict:
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    if parent := raw.pop("extends", None):
        raw = _merge(_read(path.parent / parent), raw)
    return raw


def load_config(path: str | Path | None = None) -> Config:
    """Load a config file. A file can say `extends: other.yaml` and only list overrides."""
    path = Path(path or os.environ.get("AGENT_CONFIG", DEFAULT_PATH)).resolve()
    cfg = Config(_expand(_read(path)))
    cfg.root = path.parent.parent
    return cfg


@lru_cache(maxsize=1)
def get_config() -> Config:
    return load_config()

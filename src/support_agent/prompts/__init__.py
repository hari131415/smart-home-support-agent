"""Versioned system prompts.

Prompts live as plain files (v1.md, v2.md, ...) so changes show up as diffs in
review. Every run logs the version and a content hash; the hash is what we key
eval results on, so an edit without a version bump still shows up as a change.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

PROMPT_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Prompt:
    version: str
    text: str

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()[:12]


def load_prompt(version: str) -> Prompt:
    path = PROMPT_DIR / f"{version}.md"
    if not path.exists():
        available = sorted(p.stem for p in PROMPT_DIR.glob("v*.md"))
        raise FileNotFoundError(f"prompt {version!r} not found; have {available}")
    return Prompt(version=version, text=path.read_text().strip())

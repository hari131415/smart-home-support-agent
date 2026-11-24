"""Turn device manuals into retrievable chunks.

Markdown manuals are split on `## ` headings, one chunk per section, which keeps
troubleshooting steps together instead of cutting them mid-list. PDFs (the
format most vendors publish) don't have reliable headings, so they're split into
overlapping windows instead.

Chunk ids look like `thermostat_t3#troubleshooting` and are what the agent cites.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_SECTION = re.compile(r"^## +(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    id: str
    doc: str
    device_type: str
    model: str
    section: str
    text: str

    def render(self) -> str:
        return f"[{self.id}] {self.model} - {self.section}\n{self.text}"


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def parse_markdown(path: Path) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")
    meta: dict = {}
    if m := _FRONTMATTER.match(raw):
        meta = yaml.safe_load(m.group(1)) or {}
        raw = raw[m.end() :]

    doc = path.stem
    device_type = meta.get("device_type", "unknown")
    model = meta.get("model", doc)

    headings = list(_SECTION.finditer(raw))
    chunks = []
    for i, h in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(raw)
        body = raw[h.end() : end].strip()
        if not body:
            continue
        section = h.group(1).strip()
        chunks.append(
            Chunk(
                id=f"{doc}#{slugify(section)}",
                doc=doc,
                device_type=device_type,
                model=model,
                section=section,
                text=body,
            )
        )
    return chunks


def parse_pdf(path: Path, device_type: str = "unknown", window: int = 1200, overlap: int = 200):
    from pypdf import PdfReader

    text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    text = re.sub(r"[ \t]+", " ", text)
    doc = slugify(path.stem)
    chunks, start, n = [], 0, 0
    while start < len(text):
        piece = text[start : start + window].strip()
        if piece:
            chunks.append(
                Chunk(
                    id=f"{doc}#part_{n:03d}",
                    doc=doc,
                    device_type=device_type,
                    model=path.stem,
                    section=f"part {n}",
                    text=piece,
                )
            )
            n += 1
        start += window - overlap
    return chunks


def load_manuals(manuals_dir: str | Path) -> list[Chunk]:
    manuals_dir = Path(manuals_dir)
    chunks: list[Chunk] = []
    for path in sorted(manuals_dir.iterdir()):
        if path.suffix == ".md":
            chunks.extend(parse_markdown(path))
        elif path.suffix.lower() == ".pdf":
            # PDFs can carry their device type in a sidecar: foo.pdf + foo.yaml
            sidecar = path.with_suffix(".yaml")
            dt = (
                yaml.safe_load(sidecar.read_text()).get("device_type") if sidecar.exists() else None
            )
            chunks.extend(parse_pdf(path, device_type=dt or "unknown"))

    ids = [c.id for c in chunks]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate chunk ids: {sorted(dupes)}")
    log.info("loaded %d chunks from %d files", len(chunks), len({c.doc for c in chunks}))
    return chunks


def write_chunks(chunks: list[Chunk], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c)) + "\n")


def read_chunks(path: str | Path) -> list[Chunk]:
    with open(path) as f:
        return [Chunk(**json.loads(line)) for line in f if line.strip()]

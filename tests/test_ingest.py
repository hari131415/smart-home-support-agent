import pytest

from support_agent.ingest import load_manuals, parse_markdown, read_chunks, slugify, write_chunks


def test_every_manual_produces_chunks(chunks, cfg):
    docs = {c.doc for c in chunks}
    manuals = {p.stem for p in cfg.path(cfg.retrieval["manuals_dir"]).glob("*.md")}
    assert docs == manuals


def test_chunk_ids_are_unique_and_stable(chunks):
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))
    assert "thermostat_t3#troubleshooting" in ids
    assert "smoke_co_alarm_s1#important_safety_information" in ids


def test_frontmatter_sets_device_type(chunks):
    types = {c.doc: c.device_type for c in chunks}
    assert types["smart_lock_l1"] == "smart_lock"
    assert types["indoor_camera_c1"] == "camera"


def test_sections_keep_lists_together(chunks):
    setup = next(c for c in chunks if c.id == "thermostat_t3#first_time_setup")
    # all five numbered steps should be in one chunk
    assert all(f"{i}." in setup.text for i in range(1, 6))


def test_parse_markdown_without_frontmatter(tmp_path):
    p = tmp_path / "widget.md"
    p.write_text("# Widget\n\n## Reset\nHold the button.\n\n## Empty\n\n## Warranty\n1 year.\n")
    chunks = parse_markdown(p)
    assert [c.section for c in chunks] == ["Reset", "Warranty"]
    assert chunks[0].device_type == "unknown"


def test_duplicate_ids_rejected(tmp_path):
    (tmp_path / "a.md").write_text("## Reset\nx\n\n## Reset\ny\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_manuals(tmp_path)


def test_roundtrip(chunks, tmp_path):
    write_chunks(chunks, tmp_path / "chunks.jsonl")
    assert read_chunks(tmp_path / "chunks.jsonl") == chunks


def test_slugify():
    assert slugify("Schedules, timers and away mode") == "schedules_timers_and_away_mode"


def test_production_config_extends_base():
    from support_agent.config import REPO_ROOT, load_config

    prod = load_config(REPO_ROOT / "configs" / "production.yaml")
    assert prod.devices["backend"] == "bigquery"
    assert prod.tracing["sink"] == "bigquery"
    # inherited, not overridden
    assert prod.llm["model"] == "gemini-2.5-flash"
    assert prod.devices["bq_table"] == "device_status"


def test_relative_paths_resolve_from_config_location(tmp_path):
    import shutil

    from support_agent.config import REPO_ROOT, load_config

    (tmp_path / "configs").mkdir()
    shutil.copy(REPO_ROOT / "configs" / "config.yaml", tmp_path / "configs" / "config.yaml")
    cfg = load_config(tmp_path / "configs" / "config.yaml")
    assert cfg.path("data/manuals") == tmp_path / "data" / "manuals"

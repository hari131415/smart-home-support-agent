import pytest

from support_agent.retrieval import HybridRetriever, detect_device_types, tokenize

from .fakes import HashEmbedder


@pytest.mark.parametrize(
    "query,expected",
    [
        ("thermostat shows E74", "thermostat_t3#display_and_status_messages"),
        ("how do I factory reset the smart lock", "smart_lock_l1#factory_reset"),
        ("hub light is purple", "hub_h1#status_light"),
        ("bulb flickering", "color_bulb_b2#troubleshooting"),
        ("camera won't read my microSD card", "indoor_camera_c1#troubleshooting"),
        ("plug won't connect to hotel wifi captive portal", "smart_plug_p1#troubleshooting"),
    ],
)
def test_known_queries_hit_top3(retriever, query, expected):
    ids = [h.chunk.id for h in retriever.search(query, k=3)]
    assert expected in ids, ids


def test_device_filter_keeps_results_on_device(retriever):
    hits = retriever.search("how do I reset it", k=5, device_type="doorbell")
    assert {h.chunk.device_type for h in hits} == {"doorbell"}


def test_detected_device_narrows_search(retriever):
    hits = retriever.search("doorbell factory reset", k=5)
    assert all(h.chunk.device_type == "doorbell" for h in hits)


def test_unknown_device_type_falls_back_to_everything(retriever):
    hits = retriever.search("reset", k=5, device_type="toaster")
    assert len(hits) == 5


def test_detect_device_types():
    assert detect_device_types("my CO alarm keeps chirping") == {"smoke_alarm"}
    assert detect_device_types("lock and hub both offline") == {"smart_lock", "hub"}
    assert detect_device_types("what is the weather") == set()
    # "l1" shouldn't match inside other tokens
    assert detect_device_types("call1 me") == set()


def test_tokenize_keeps_error_codes_and_versions():
    toks = tokenize("Error E74 on firmware 7.1 while flickering")
    assert "e74" in toks and "7.1" in toks and "flicker" in toks


def test_hybrid_with_dense(chunks, tmp_path):
    r = HybridRetriever(chunks, embedder=HashEmbedder(), cache_dir=tmp_path)
    hits = r.search("thermostat E74 error", k=3)
    assert hits[0].dense is not None
    assert "thermostat_t3#display_and_status_messages" in [h.chunk.id for h in hits]
    # second build should load from cache, not re-embed
    assert (tmp_path / "vectors.npz").exists()
    r2 = HybridRetriever(chunks, embedder=HashEmbedder(), cache_dir=tmp_path)
    assert (r2.vectors == r.vectors).all()


def test_query_embedding_error_falls_back_to_bm25(chunks, tmp_path):
    class QuotaExceeded(HashEmbedder):
        def embed_query(self, text):
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

    HybridRetriever(chunks, embedder=HashEmbedder(), cache_dir=tmp_path)  # cache the vectors
    r = HybridRetriever(chunks, embedder=QuotaExceeded(), cache_dir=tmp_path)
    hits = r.search("factory reset the hub", k=3)
    assert hits[0].chunk.id == "hub_h1#reset"
    assert hits[0].dense is None and r.dense_failures == 1

"""P3.2 — reranker dei chunk di contesto. Unit test: nessun DB, nessun LLM reale."""

from __future__ import annotations

import pytest

from backend.memory import reranker
from backend.memory.reranker import LLMReranker, _RerankVerdict, _sanitize, rerank_passages


class FakeLLM:
    """with_structured_output stub: ritorna un _RerankVerdict fisso (o solleva)."""

    def __init__(self, order=None, *, raises: bool = False, as_dict: bool = False):
        self._order = order
        self._raises = raises
        self._as_dict = as_dict
        self.calls: list = []

    def invoke(self, messages):
        self.calls.append(messages)
        if self._raises:
            raise RuntimeError("boom")
        if self._as_dict:
            return {"order": self._order}
        return _RerankVerdict(order=list(self._order or []))


class FakeReranker:
    def __init__(self, order):
        self._order = order

    def order(self, query, passages):
        return list(self._order)


# --- _sanitize ---------------------------------------------------------


@pytest.mark.parametrize(
    "raw, n, expected",
    [
        ([2, 0, 1], 3, [2, 0, 1]),
        ([1], 3, [1, 0, 2]),               # mancanti in coda, ordine originale
        ([5, 1, 5, -1, "x", 0], 3, [1, 0, 2]),  # fuori range / dup / non-int scartati
        ([], 3, [0, 1, 2]),
        (None, 2, [0, 1]),
    ],
)
def test_sanitize(raw, n, expected):
    assert _sanitize(raw, n) == expected


# --- LLMReranker ------------------------------------------------------


def test_llm_reranker_applies_order():
    r = LLMReranker(FakeLLM([2, 0, 1]))
    assert r.order("q", ["a", "b", "c"]) == [2, 0, 1]


def test_llm_reranker_accepts_dict_output():
    r = LLMReranker(FakeLLM([1, 0], as_dict=True))
    assert r.order("q", ["a", "b", "c"]) == [1, 0, 2]


def test_llm_reranker_falls_back_to_identity_on_error():
    llm = FakeLLM(raises=True)
    r = LLMReranker(llm)
    assert r.order("q", ["a", "b", "c"]) == [0, 1, 2]
    assert len(llm.calls) == 1


def test_llm_reranker_skips_trivial_input():
    llm = FakeLLM([0])
    r = LLMReranker(llm)
    assert r.order("q", ["only"]) == [0]
    assert r.order("q", []) == []
    assert llm.calls == []  # <=1 passaggio: nessuna chiamata


# --- rerank_passages ------------------------------------------------


def _items(*texts):
    return [{"content": t, "score": i} for i, t in enumerate(texts)]


def test_rerank_passages_reorders_and_tags_position():
    items = _items("alpha", "beta", "gamma")
    out = rerank_passages("q", items, reranker=FakeReranker([2, 0, 1]))
    assert [c["content"] for c in out] == ["gamma", "alpha", "beta"]
    assert [c["rerank_position"] for c in out] == [0, 1, 2]
    assert out[0]["score"] == 2  # gli altri campi restano


def test_rerank_passages_passthrough_when_no_reranker_available(monkeypatch):
    monkeypatch.setattr(reranker, "build_reranker", lambda: None)
    items = _items("a", "b")
    assert rerank_passages("q", items) == items


def test_rerank_passages_passthrough_without_query():
    items = _items("a", "b", "c")
    out = rerank_passages("   ", items, reranker=FakeReranker([2, 1, 0]), top_n=2)
    assert out == items[:2]


def test_rerank_passages_top_n_truncates():
    items = _items("a", "b", "c", "d")
    out = rerank_passages("q", items, reranker=FakeReranker([3, 2, 1, 0]), top_n=2)
    assert [c["content"] for c in out] == ["d", "c"]


def test_rerank_passages_preserves_tail_beyond_cap(monkeypatch):
    monkeypatch.setattr(reranker, "MAX_PASSAGES", 2)
    items = _items("a", "b", "c", "d")
    out = rerank_passages("q", items, reranker=FakeReranker([1, 0]))
    # head [a,b] riordinato -> [b,a]; tail [c,d] invariato in coda
    assert [c["content"] for c in out] == ["b", "a", "c", "d"]
    assert "rerank_position" not in out[2]  # il tail non e' passato dal giudice


def test_build_reranker_none_without_key(monkeypatch):
    monkeypatch.setattr(reranker.settings, "openai_api_key", None)
    reranker.build_reranker.cache_clear()
    assert reranker.build_reranker() is None
    reranker.build_reranker.cache_clear()

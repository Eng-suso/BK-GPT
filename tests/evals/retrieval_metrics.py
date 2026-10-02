"""Quanto il retrieval porta all'agente i passi giusti, in numeri.

Il retrieval non si giudica dalla risposta finale: una risposta buona puo'
nascere da un contesto sbagliato (il modello sapeva gia'), una cattiva da un
contesto giusto (il modello non l'ha usato). Qui si misura solo il primo
tratto: per una domanda, i chunk restituiti contengono i passi delle fonti che
un consulente indicherebbe?

| metrica | cosa misura |
| --- | --- |
| recall@k | quota dei passi attesi che compaiono nei primi k chunk |
| precision@k | quota dei primi k chunk che contengono almeno un passo atteso |
| MRR | 1 / posizione del primo chunk utile: quanto presto arriva qualcosa di buono |
| nDCG@k | l'ordine: i chunk utili stanno in cima o in fondo ai k? |

La rilevanza e' testuale e deterministica: un chunk e' utile per un passo se lo
contiene, a meno degli spazi. I passi sono citati alla lettera dalle fonti, e
un test L0 lo verifica come per il golden set.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SPACES = re.compile(r"\s+")


def flat(text: str) -> str:
    """Spazi normalizzati: il chunker ricompone gli a capo della fonte."""
    return _SPACES.sub(" ", text or "").strip()


def passages_in(chunk: str, passages: list[str]) -> set[int]:
    """Gli indici dei passi attesi che il chunk contiene."""
    body = flat(chunk)
    return {index for index, passage in enumerate(passages) if flat(passage) in body}


@dataclass
class QueryResult:
    query_id: str
    recall_at_k: float
    precision_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float
    missed_passages: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "recall_at_k": self.recall_at_k,
            "precision_at_k": self.precision_at_k,
            "reciprocal_rank": self.reciprocal_rank,
            "ndcg_at_k": self.ndcg_at_k,
            "missed_passages": self.missed_passages,
        }


def score_query(
    query_id: str,
    ranked_chunks: list[str],
    passages: list[str],
    *,
    k: int,
    relevant_in_corpus: int,
) -> QueryResult:
    """Le quattro metriche per una domanda.

    `relevant_in_corpus` e' il numero di chunk dell'intero corpus che contengono
    almeno un passo atteso: e' il meglio che un retrieval perfetto potrebbe
    mettere nei primi k, e fa da denominatore all'nDCG ideale.
    """
    top = ranked_chunks[:k]
    hits = [passages_in(chunk, passages) for chunk in top]
    found = set().union(*hits) if hits else set()
    useful = [bool(hit) for hit in hits]

    recall = round(len(found) / len(passages), 4) if passages else 1.0
    precision = round(sum(useful) / len(top), 4) if top else 0.0
    first = next((rank for rank, ok in enumerate(useful, start=1) if ok), None)
    reciprocal_rank = round(1 / first, 4) if first else 0.0

    dcg = sum(1 / math.log2(rank + 1) for rank, ok in enumerate(useful, start=1) if ok)
    ideal_hits = min(k, relevant_in_corpus)
    idcg = sum(1 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    ndcg = round(dcg / idcg, 4) if idcg else 0.0

    return QueryResult(
        query_id=query_id,
        recall_at_k=recall,
        precision_at_k=precision,
        reciprocal_rank=reciprocal_rank,
        ndcg_at_k=ndcg,
        missed_passages=[passage for index, passage in enumerate(passages) if index not in found],
    )


RETRIEVAL_METRICS = ("recall_at_k", "precision_at_k", "mrr", "ndcg_at_k")


def aggregate(results: list[QueryResult]) -> dict[str, float]:
    """Le medie sulle domande: e' il numero che si confronta con la baseline."""
    if not results:
        return {name: 0.0 for name in RETRIEVAL_METRICS}
    count = len(results)
    return {
        "recall_at_k": round(sum(item.recall_at_k for item in results) / count, 4),
        "precision_at_k": round(sum(item.precision_at_k for item in results) / count, 4),
        "mrr": round(sum(item.reciprocal_rank for item in results) / count, 4),
        "ndcg_at_k": round(sum(item.ndcg_at_k for item in results) / count, 4),
    }


def retrieval_regressions(
    current: dict[str, float], baseline: dict[str, float], *, tolerance: float = 0.02
) -> list[str]:
    """Le medie scese oltre la tolleranza.

    Il ramo lessicale e' deterministico: la tolleranza assorbe solo gli
    arrotondamenti e un ordine diverso fra chunk a pari punteggio.
    """
    return [
        f"{name} {baseline[name]:.3f} -> {current.get(name, 0.0):.3f}"
        for name in RETRIEVAL_METRICS
        if name in baseline and current.get(name, 0.0) < baseline[name] - tolerance
    ]


# --- il dataset ----------------------------------------------------------------


@dataclass(frozen=True)
class Passage:
    source: str
    quote: str


@dataclass(frozen=True)
class RetrievalQuery:
    id: str
    case: str
    query: str
    passages: list[Passage]


@dataclass(frozen=True)
class RetrievalSet:
    k: int
    queries: list[RetrievalQuery]

    @classmethod
    def load(cls, path: Path) -> "RetrievalSet":
        data = json.loads(path.read_text(encoding="utf-8"))
        queries = [
            RetrievalQuery(
                id=item["id"],
                case=item["case"],
                query=item["query"],
                passages=[Passage(source=p["source"], quote=p["quote"]) for p in item["passages"]],
            )
            for item in data["queries"]
        ]
        ids = [query.id for query in queries]
        if len(ids) != len(set(ids)):
            raise ValueError("domande con lo stesso id nel dataset di retrieval")
        return cls(k=int(data["k"]), queries=queries)

"""Gateway unico di lettura del cervello (INV-9).

Nessun tool o agente interroga Neo4j / Postgres-KG / Mem0 direttamente: si
passa da qui, che inietta lo scope (`consultant_id`, `client_id`) in ogni
query. Con Neo4j Community senza subgraph ACL, e con Mem0 senza tenant ACL,
questo e' l'unico punto di enforcement in lettura.

`graph_retrieve` (grafo tipizzato, retrieval ibrido — P3):
  0. confine di lettura — `scope_project_id` / `scope_process_id` delimitano
     l'evidenza leggibile: solo le righe di quel processo (piu' quelle
     project-level senza processo), mai quelle di un altro processo o progetto
     dello stesso cliente. Senza uno dei due la chiamata e' rifiutata, a meno
     che il chiamante dichiari `allow_client_wide=True` (letture consultant /
     cliente, es. cutover e sweep). Il write path e' sempre stato scoped
     (`canonical.write_*` stampa project_id/process_id); questo e' il lato in
     lettura dello stesso confine — vedi PROCESS-V2-08.
  1. seed entita' — nomi entita' + parole della query -> match esatto/alias/LIKE
     su kg_entity (Postgres, RLS per client), ristretto allo scope
  2. ricerca testo su kg_chunk (`_text_search`), due segnali fusi con RRF:
       - lessicale: `content_tsv @@ websearch_to_tsquery` + `ts_rank_cd`
       - vettoriale: cosine sull'embedding della query (se l'embedder c'e')
     dai chunk fusi si risale ai `source_id` -> entita' con quella provenance,
     ordinate per rank del miglior chunk.
  3. fusione RRF di (seed entita', entita' da provenance) -> lista seed unica
  4. espansione — k-hop in Neo4j dai seed, ogni nodo del path filtrato per
     client_id e, in una lettura scoped, per l'insieme dei nodi leggibili
     calcolato in Postgres (cosi' il `limit` non si spende su triple che
     l'idratazione scartera'). Budget per seed, uscita a turni, hub non
     attraversati (`_expand`, GR-02/GR-03).
  5. idratazione — ogni id opaco -> testo autoritativo da Postgres (RLS):
     canonical_name, statement, title, ... In idratazione lo scope viene
     riapplicato: un nodo che Neo4j ha portato dentro il path ma che in
     Postgres appartiene a un altro processo viene scartato, e con lui la
     tripla. Neo4j non e' il confine: Postgres lo e'.
  6. rerank opzionale (`settings.retrieval_rerank_enabled`, default off) — un
     giudice LLM riordina i `chunks` di contesto per rilevanza alla query.
  I chunk fusi tornano come contesto testuale (`chunks`). `truncated` dice se il
  budget ha tagliato; `staleness` compare solo se la proiezione di quel cliente
  e' indietro rispetto a Postgres (GR-01).

`memory_search` (recall Mem0):
  - `user_id` Mem0 = mappa dal `consultant_id`
  - post-filtro per `client_id` sui metadata: le memorie consultant-level
    (senza client_id) restano visibili ovunque, quelle client-scoped solo
    nel loro cliente

`workspace_read` (stato operativo):
  - snapshot scoped della workspace (Postgres, SoT operativa INV-8): project +
    processi + sources/decisions, filtrati per `process_ids`

Disattivato in silenzio se canonical / Neo4j / Mem0 non sono configurati: i
chiamanti degradano con uno status esplicito.

Il pacchetto e' la facciata: chi legge importa da qui. Dentro, un modulo per
capacita' - `scope` (il confine di lettura), `text_search` (seed e chunk),
`graph` (`graph_retrieve`), `ledger` (`claim_ledger`), `memory`
(`memory_search`), `procedural` (`procedural_retrieve`), `workspace`
(`workspace_read`).
"""

from __future__ import annotations

from backend.memory.gateway.graph import graph_retrieve
from backend.memory.gateway.ledger import claim_ledger
from backend.memory.gateway.memory import memory_search
from backend.memory.gateway.procedural import procedural_retrieve
from backend.memory.gateway.scope import (
    ReadScope,
    graph_available,
    memory_available,
    procedural_available,
)
from backend.memory.gateway.workspace import workspace_read

__all__ = [
    "ReadScope",
    "claim_ledger",
    "graph_available",
    "graph_retrieve",
    "memory_available",
    "memory_search",
    "procedural_available",
    "procedural_retrieve",
    "workspace_read",
]

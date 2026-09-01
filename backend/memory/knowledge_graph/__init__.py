"""Knowledge graph canonical: Postgres autorevole, proiezione su Neo4j.

Sottomoduli:
  - ``catalog``     — nodi/archi proiettabili + guardrail B+ (INV-5)
  - ``canonical``   — porta di scrittura (write_entity/relation/claim/... e
                      ``write_evidence`` atomico) verso il canonical Postgres
  - ``projector``   — payload outbox -> Cypher (MERGE / DETACH DELETE)
  - ``neo4j_store`` — driver Neo4j + purge per client
  - ``mirror``      — traduce l'evidenza dei toolset e chiama ``write_evidence``

La lettura passa da ``backend.memory.gateway`` (INV-9), mai da qui.
"""

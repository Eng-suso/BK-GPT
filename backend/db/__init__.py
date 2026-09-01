"""Accesso al Postgres canonical (piano "Cervello DeliR").

Ogni lettura/scrittura sul DB canonical passa da `canonical_session()`, che apre
una transazione impostando il contesto RLS (app.current_consultant_id /
app.current_client_id). L'app si connette come ruolo delir_app: NOBYPASSRLS,
non-owner, solo DML.

Separato di proposito da backend.database (SQLite chat history), che ha la sua
traccia di migrazione.
"""

from backend.db.session import canonical_engine, canonical_session

__all__ = ["canonical_engine", "canonical_session"]

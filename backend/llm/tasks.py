"""Il registro dei compiti: chi chiama dichiara *cosa* sta facendo, non *come*.

Prima di questo registro ogni modulo costruiva il suo client e scegliva i suoi
parametri. Il risultato: dieci punti di chiamata, `reasoning_effort="medium"` per
sette compiti diversi - un default, non una scelta - e nessun posto in cui
guardare per sapere quanto costa un'estrazione rispetto a un rerank.

Qui il compito e' un nome, e il profilo e' un dato. Cambiare il modello di un
compito e' cambiare una riga di questa tabella, e la si cambia sui numeri:
il costo dal registro dei consumi, la qualita' dal golden set.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from backend.settings import settings


class LlmTask(StrEnum):
    """I compiti per cui DeliR chiama un modello.

    Il valore e' la stringa che finisce nel registro dei consumi, quindi non si
    rinomina a cuor leggero: spezzerebbe la continuita' delle serie storiche.
    """

    PLAN_EXTRACTION = "plan_extraction"
    PLAN_QUALITY = "plan_quality"
    PLAN_UNIFICATION = "plan_unification"
    CONFORMANCE_AUDIT = "conformance_audit"
    ENTITY_RESOLUTION = "entity_resolution"
    RETRIEVAL_RERANK = "retrieval_rerank"
    PLAYBOOK_EXTRACTION = "playbook_extraction"
    PLAYBOOK_GENERALIZATION = "playbook_generalization"
    CHAT_TURN = "chat_turn"
    CONTEXT_ROUTING = "context_routing"
    EMBEDDING = "embedding"
    TRANSCRIPTION = "transcription"


@dataclass(frozen=True, slots=True)
class TaskProfile:
    """Come si esegue un compito.

    Attributes:
        task: Il compito.
        reasoning_effort: Quanto ragionamento pagare. `"none"` dove l'output e'
            uno schema strict e lo schema fa il lavoro; piu' alto dove la
            difficolta' e' nel giudizio e non nella forma.
        max_output_tokens: Tetto sull'uscita, o `None` per il default del client.
        retry: Se il gateway puo' ritentare questo compito. Un compito lungo con
            una coda dietro non si ritenta qui: si lascia fallire e la coda lo
            riprende con il suo backoff.
        deferrable: Se il lavoro puo' aspettare. Serve a decidere, piu' avanti,
            cosa puo' passare da Batch/Flex - e Batch non e' per la chat ne' per
            un'intervista che il consulente sta aspettando.
        scales_with_input: Se il timeout deve seguire la lunghezza dell'input.
            Vero per le estrazioni; falso per un rerank, che legge poco.
        model_name: Il modello, quando il compito **non** puo' usare quello di
            conversazione. Serve all'embedding, che ha un modello suo e una
            dimensione vincolata dallo schema del database (INV-4).
    """

    task: LlmTask
    reasoning_effort: str = "low"
    max_output_tokens: int | None = None
    retry: bool = False
    deferrable: bool = False
    scales_with_input: bool = True
    model_name: str | None = None

    @property
    def model(self) -> str:
        """Il modello del compito.

        Per i compiti di conversazione oggi e' uno solo, dai settings: scegliere
        per compito e' P4, e va fatto con gli eval in mano, non a intuito. Il
        punto di questo registro e' che quando quel giorno arriva si cambia
        **qui**, e non in dieci moduli.

        L'embedding fa eccezione e non e' una scelta di qualita': il suo modello
        decide la dimensione dei vettori gia' scritti, quindi e' un contratto,
        non un parametro.
        """
        return self.model_name or settings.openai_model


# Profili di partenza. Le note dicono *perche'* un valore e' quello: senza la
# ragione, il prossimo che passa lo cambia a intuito.
_PROFILES: dict[LlmTask, TaskProfile] = {
    # L'estrazione e' il compito dove si concentrano i difetti di qualita', e un
    # risultato che non passa i controlli costa due chiamate invece di una. Qui
    # il ragionamento si paga volentieri.
    LlmTask.PLAN_EXTRACTION: TaskProfile(
        LlmTask.PLAN_EXTRACTION, reasoning_effort="medium", scales_with_input=True
    ),
    LlmTask.PLAN_QUALITY: TaskProfile(
        LlmTask.PLAN_QUALITY, reasoning_effort="low", scales_with_input=True
    ),
    LlmTask.PLAN_UNIFICATION: TaskProfile(
        LlmTask.PLAN_UNIFICATION, reasoning_effort="medium", scales_with_input=True
    ),
    # Il revisore decide se un piano regge contro le fonti: e' giudizio, non
    # forma. Non ha una versione economica (L7: si fa intera o si rimanda).
    LlmTask.CONFORMANCE_AUDIT: TaskProfile(
        LlmTask.CONFORMANCE_AUDIT, reasoning_effort="medium", scales_with_input=True
    ),
    # Questi due arrivano al modello solo sui casi che il codice non ha chiuso, e
    # rispondono dentro uno schema strict: lo schema fa il lavoro.
    LlmTask.ENTITY_RESOLUTION: TaskProfile(
        LlmTask.ENTITY_RESOLUTION, reasoning_effort="none", scales_with_input=False
    ),
    LlmTask.RETRIEVAL_RERANK: TaskProfile(
        LlmTask.RETRIEVAL_RERANK, reasoning_effort="none", scales_with_input=False
    ),
    # Arricchimento della memoria: nessuno lo sta aspettando davanti a uno
    # schermo, quindi e' il primo candidato per il lavoro differito.
    LlmTask.PLAYBOOK_EXTRACTION: TaskProfile(
        LlmTask.PLAYBOOK_EXTRACTION, reasoning_effort="low", deferrable=True
    ),
    LlmTask.PLAYBOOK_GENERALIZATION: TaskProfile(
        LlmTask.PLAYBOOK_GENERALIZATION, reasoning_effort="low", deferrable=True
    ),
    # La chat ritenta perche' dietro non c'e' nessuna coda: il guasto arriva al
    # consulente a meta' conversazione. `reasoning_effort="none"` e' cio' che
    # `agent.py` passa gia' oggi.
    LlmTask.CHAT_TURN: TaskProfile(
        LlmTask.CHAT_TURN, reasoning_effort="none", retry=True, scales_with_input=False
    ),
    LlmTask.CONTEXT_ROUTING: TaskProfile(
        LlmTask.CONTEXT_ROUTING,
        reasoning_effort="none",
        max_output_tokens=512,
        retry=True,
        scales_with_input=False,
    ),
    # L'embedding non sceglie: il modello e la dimensione sono il contratto v1 del
    # knowledge graph (INV-4), e cambiarli invalida i vettori gia' scritti. Il
    # valore e' lo stesso di `backend.memory.embeddings.EMBED_MODEL`, ed e' scritto
    # qui a mano per non far dipendere il registro dei compiti dalla memoria: un
    # test tiene i due allineati.
    LlmTask.EMBEDDING: TaskProfile(
        LlmTask.EMBEDDING,
        reasoning_effort="none",
        scales_with_input=False,
        model_name="text-embedding-3-small",
    ),
    # Come la chat: c'e' un upload in corso, e rifarlo costa piu' del retry.
    LlmTask.TRANSCRIPTION: TaskProfile(
        LlmTask.TRANSCRIPTION, reasoning_effort="none", retry=True, scales_with_input=False
    ),
}


def profile_for(task: LlmTask) -> TaskProfile:
    """Il profilo di un compito.

    Raises:
        KeyError: Se un compito e' dichiarato nell'enum ma non ha un profilo. E'
            un errore di programmazione, non una configurazione mancante: un
            default silenzioso qui rimetterebbe in piedi il `medium` per tutto.
    """
    return _PROFILES[task]


def all_profiles() -> dict[LlmTask, TaskProfile]:
    """Tutti i profili, per i test di completezza e per esporli in diagnostica."""
    return dict(_PROFILES)

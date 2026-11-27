"""Dove escono i dati: l'elenco delle destinazioni, risolto dalla configurazione.

Perche' esiste. «Quali fornitori ricevono i dati del cliente, e quali dati» e' la
prima domanda di ogni questionario di sicurezza e di ogni DPA. Prima la risposta
stava sparsa in dieci moduli: la chat su `openai_base_url`, gli embedding e la
trascrizione sempre su api.openai.com (anche quando la chat andava altrove), la
trascrizione live su un URL scritto a mano, Mem0 sul suo endpoint, LangSmith con
i prompt interi, Tavily con le query dell'agente. Nessuno poteva elencarli senza
leggere il codice, e il primo LLM aggiunto alla pipeline li avrebbe moltiplicati.

Qui ogni destinazione e' un dato: cosa esce, verso quale host, per quali compiti,
e se e' attiva con la configurazione di adesso. Chi costruisce un client verso
l'esterno chiede prima il permesso a `require()`; il registro e quello che gira
davvero non possono divergere, perche' sono la stessa funzione.

La regola (SEC-06, gate G3 del riferimento di sicurezza):

- un host interno (loopback, rete privata, nome di servizio docker senza punti)
  e' self-hosted: i dati non lasciano il perimetro;
- un host esterno, in un ambiente vero (staging, prod), deve stare in
  `DELIR_EGRESS_ALLOWED_HOSTS`. Altrimenti l'app non parte, e se ci arrivasse
  la chiamata viene rifiutata: fail closed;
- in sviluppo, una lista vuota vuol dire «tutto permesso»; una lista non vuota
  vale anche li', cosi' la regola si prova prima del deploy.

Il giorno in cui un compito passa a un altro modello o a un altro fornitore, si
cambia `_llm_url_for()` e il resto - inventario, controllo all'avvio, pannello
della UI - segue da solo.
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlparse

from backend.llm.providers import Provider
from backend.llm.tasks import MEM0_TASKS, NON_CHAT_TASKS, LlmTask, profile_for
from backend.llm_config import MissingProviderKey
from backend.settings import environment_is_open, langsmith_tracing_enabled, settings

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1"
ANTHROPIC_API_URL = "https://api.anthropic.com"
OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime?intent=transcription"
TAVILY_API_URL = "https://api.tavily.com"


class DataCategory(StrEnum):
    """Cosa contiene quello che esce. Il valore finisce nell'API e nella UI."""

    #: Interviste, documenti caricati, messaggi della chat: puo' contenere dati
    #: personali dei dipendenti del cliente e informazioni commerciali riservate.
    CUSTOMER_CONTENT = "customer_content"
    #: La voce registrata: e' un dato personale di per se', prima ancora del testo.
    AUDIO = "audio"
    #: Prompt e risposte interi, cosi' come li vede il modello: un servizio di
    #: tracing riceve tutto quello che riceve il modello.
    PROMPT_TRACE = "prompt_trace"
    #: Query di ricerca generate dall'agente: brevi, ma possono citare il cliente.
    SEARCH_QUERY = "search_query"
    #: Modelli BPMN e scenari di simulazione: nomi di attivita' e ruoli.
    PROCESS_MODEL = "process_model"
    #: Chi usa DeliR: email e identificativo del consulente presso il fornitore
    #: di autenticazione. Non contenuti del cliente.
    USER_IDENTITY = "user_identity"


class Destination(StrEnum):
    """Le destinazioni conosciute. Il valore e' la chiave stabile nel registro."""

    LLM_CHAT = "llm_chat"
    LLM_CLAUDE = "llm_claude"
    LLM_EMBEDDING = "llm_embedding"
    TRANSCRIPTION = "transcription"
    TRANSCRIPTION_LIVE = "transcription_live"
    MEMORY_EXTRACTION = "memory_extraction"
    MEMORY_EMBEDDING = "memory_embedding"
    TRACING = "tracing"
    WEB_SEARCH = "web_search"
    DOCUMENT_READER = "document_reader"
    SIMULATION_ENGINE = "simulation_engine"
    IDENTITY_PROVIDER = "identity_provider"


@dataclass(frozen=True, slots=True)
class EgressRoute:
    """Una destinazione risolta con la configurazione di adesso.

    Attributes:
        destination: Quale destinazione.
        purpose: A cosa serve, in una riga leggibile da chi compila un DPA.
        url: L'indirizzo effettivo.
        data: Cosa contiene quello che esce.
        active: Se con questa configurazione qualcosa esce davvero. Una
            destinazione spenta resta nell'elenco: «non usata» e' un'informazione.
        tasks: I compiti del gateway che passano di qui.
    """

    destination: Destination
    purpose: str
    url: str
    data: tuple[DataCategory, ...]
    active: bool
    tasks: tuple[LlmTask, ...] = field(default=())

    @property
    def host(self) -> str:
        return (urlparse(self.url).hostname or "").lower()

    @property
    def internal(self) -> bool:
        return is_internal_host(self.host)


class EgressBlocked(MissingProviderKey):
    """Una destinazione esterna non e' autorizzata: la chiamata non parte.

    E' configurazione, come la chiave mancante, e chi chiama la tratta allo
    stesso modo: esito `configuration_error`, niente retry. Per questo ne e'
    una sottoclasse invece di un'eccezione nuova che nessuno intercetterebbe.
    """


_NON_CHAT_TASKS = NON_CHAT_TASKS
# I compiti di Mem0 non passano dal client della chat: li esegue la libreria con
# i suoi client, verso le sue destinazioni (`MEMORY_EXTRACTION`,
# `MEMORY_EMBEDDING`). Elencarli sotto `llm_chat` direbbe un fornitore sbagliato.
_MEM0_TASKS = MEM0_TASKS


def is_internal_host(host: str) -> bool:
    """Vero quando l'host non porta i dati fuori dal perimetro di chi installa.

    Un nome senza punti e' un servizio della rete docker (`docling`,
    `prosimos`) o `localhost`. Un nome con punti e' esterno anche se oggi
    risolve a un indirizzo privato: la risoluzione puo' cambiare, il nome no.
    """
    host = (host or "").strip().lower().strip("[]")
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host
    return address.is_loopback or address.is_private or address.is_link_local


def _llm_url_for(task: LlmTask) -> str:
    """L'endpoint di un compito. Oggi due: chat su `openai_base_url`, il resto su OpenAI.

    Embedding e trascrizione non seguono `openai_base_url` di proposito: la
    dimensione dei vettori e' un contratto dello schema (INV-4) e la
    trascrizione ha un modello suo. E' il punto da cambiare quando un compito
    passa a un fornitore diverso.
    """
    if task in _NON_CHAT_TASKS:
        return OPENAI_API_URL
    if profile_for(task).provider is Provider.ANTHROPIC:
        return ANTHROPIC_API_URL
    return (settings.openai_base_url or OPENAI_API_URL).rstrip("/")


def _tasks_for(url: str, *, chat: bool) -> tuple[LlmTask, ...]:
    return tuple(
        task
        for task in LlmTask
        if task not in _MEM0_TASKS
        and (task not in _NON_CHAT_TASKS) == chat
        and _llm_url_for(task) == url
    )


def routes() -> list[EgressRoute]:
    """Tutte le destinazioni, attive e no, con la configurazione corrente."""
    has_key = bool(settings.openai_api_key)
    mem0_on = has_key and bool(settings.mem0_database_url)
    chat_url = _llm_url_for(LlmTask.CHAT_TURN)
    claude_tasks = _tasks_for(ANTHROPIC_API_URL, chat=True)
    return [
        EgressRoute(
            Destination.LLM_CHAT,
            "Modello linguistico: chat, estrazione dei processi, revisione, simulazione assistita",
            chat_url,
            (DataCategory.CUSTOMER_CONTENT,),
            has_key,
            _tasks_for(chat_url, chat=True),
        ),
        EgressRoute(
            Destination.LLM_CLAUDE,
            "Modello linguistico Claude (Anthropic): i compiti scelti in LLM_TASK_MODELS_JSON",
            ANTHROPIC_API_URL,
            (DataCategory.CUSTOMER_CONTENT,),
            bool(settings.anthropic_api_key) and bool(claude_tasks),
            claude_tasks,
        ),
        EgressRoute(
            Destination.LLM_EMBEDDING,
            "Embedding dei frammenti di documenti e interviste per la ricerca",
            OPENAI_API_URL,
            (DataCategory.CUSTOMER_CONTENT,),
            has_key,
            (LlmTask.EMBEDDING,),
        ),
        EgressRoute(
            Destination.TRANSCRIPTION,
            "Trascrizione dei file audio delle interviste",
            OPENAI_API_URL,
            (DataCategory.AUDIO, DataCategory.CUSTOMER_CONTENT),
            has_key,
            (LlmTask.TRANSCRIPTION,),
        ),
        EgressRoute(
            Destination.TRANSCRIPTION_LIVE,
            "Trascrizione in diretta dal microfono",
            OPENAI_REALTIME_URL,
            (DataCategory.AUDIO, DataCategory.CUSTOMER_CONTENT),
            has_key,
            (LlmTask.LIVE_TRANSCRIPTION,),
        ),
        EgressRoute(
            Destination.MEMORY_EXTRACTION,
            "Estrazione dei fatti da ricordare (Mem0)",
            (settings.mem0_llm_base_url or OPENAI_API_URL).rstrip("/"),
            (DataCategory.CUSTOMER_CONTENT,),
            mem0_on,
            (LlmTask.MEMORY_EXTRACTION,),
        ),
        EgressRoute(
            Destination.MEMORY_EMBEDDING,
            "Embedding delle memorie (Mem0)",
            OPENAI_API_URL,
            (DataCategory.CUSTOMER_CONTENT,),
            mem0_on,
            (LlmTask.MEMORY_EMBEDDING,),
        ),
        EgressRoute(
            Destination.TRACING,
            "Tracing delle chiamate al modello (LangSmith)",
            settings.langsmith_endpoint,
            (DataCategory.PROMPT_TRACE, DataCategory.CUSTOMER_CONTENT),
            langsmith_tracing_enabled(),
        ),
        EgressRoute(
            Destination.WEB_SEARCH,
            "Ricerca web dell'agente (Tavily)",
            TAVILY_API_URL,
            (DataCategory.SEARCH_QUERY,),
            bool(settings.tavily_api_key),
        ),
        EgressRoute(
            Destination.DOCUMENT_READER,
            "Lettura di PDF, DOCX e PPTX (docling-serve)",
            settings.docling_serve_url,
            (DataCategory.CUSTOMER_CONTENT,),
            True,
        ),
        EgressRoute(
            Destination.SIMULATION_ENGINE,
            "Motore di simulazione (Prosimos)",
            settings.prosimos_base_url,
            (DataCategory.PROCESS_MODEL,),
            True,
        ),
        EgressRoute(
            Destination.IDENTITY_PROVIDER,
            "Autenticazione dei consulenti (Supabase Auth): login e chiavi pubbliche delle sessioni",
            settings.supabase_url or "https://supabase.invalid",
            (DataCategory.USER_IDENTITY,),
            settings.delir_auth_enabled and settings.delir_auth_provider == "supabase",
        ),
    ]


def route(destination: Destination) -> EgressRoute:
    return next(item for item in routes() if item.destination == destination)


def allowed_hosts() -> set[str]:
    return {
        item.strip().lower()
        for item in (settings.delir_egress_allowed_hosts or "").split(",")
        if item.strip()
    }


def is_allowed(item: EgressRoute) -> bool:
    """La regola, in un posto solo. Vedi il docstring del modulo."""
    if item.internal:
        return True
    allowed = allowed_hosts()
    if not allowed:
        return environment_is_open()
    return item.host in allowed


def require(destination: Destination) -> EgressRoute:
    """Il permesso di uscire, chiesto da chi sta per costruire un client.

    Raises:
        EgressBlocked: Se la destinazione e' esterna e non autorizzata.
    """
    item = route(destination)
    if not is_allowed(item):
        raise EgressBlocked(
            f"Invio a {item.host} ({destination.value}) non autorizzato: aggiungi "
            "l'host a DELIR_EGRESS_ALLOWED_HOSTS dopo averlo registrato fra i "
            "fornitori (docs/compliance/fornitori-e-invii-dati.md)."
        )
    return item


def require_for_task(task: LlmTask) -> EgressRoute:
    """Come `require`, per un compito del gateway."""
    if task == LlmTask.EMBEDDING:
        return require(Destination.LLM_EMBEDDING)
    if task == LlmTask.TRANSCRIPTION:
        return require(Destination.TRANSCRIPTION)
    if task not in _NON_CHAT_TASKS and profile_for(task).provider is Provider.ANTHROPIC:
        return require(Destination.LLM_CLAUDE)
    return require(Destination.LLM_CHAT)


def assert_egress_is_defensible() -> None:
    """All'avvio: nessuna destinazione attiva esce senza essere autorizzata.

    Raises:
        RuntimeError: Con l'elenco di tutte le destinazioni bloccate, non solo
            della prima: chi configura le sistema in un giro.
    """
    blocked = [item for item in routes() if item.active and not is_allowed(item)]
    if blocked:
        dettaglio = ", ".join(f"{item.destination.value} -> {item.host}" for item in blocked)
        raise RuntimeError(
            f"DELIR_ENVIRONMENT={settings.delir_environment}: destinazioni esterne non "
            f"autorizzate ({dettaglio}). Registra il fornitore in "
            "docs/compliance/fornitori-e-invii-dati.md e aggiungi l'host a "
            "DELIR_EGRESS_ALLOWED_HOSTS, oppure spegni la funzione."
        )
    for item in routes():
        if item.active and not item.internal:
            logger.info("invio dati esterno attivo: %s -> %s", item.destination.value, item.host)


def inventory() -> dict:
    """L'elenco per l'API e per il pannello: niente chiavi, solo destinazioni."""
    return {
        "environment": settings.delir_environment,
        "enforced": bool(allowed_hosts()) or not environment_is_open(),
        "routes": [
            {
                "destination": item.destination.value,
                "purpose": item.purpose,
                "host": item.host,
                "internal": item.internal,
                "active": item.active,
                "allowed": is_allowed(item),
                "data": [category.value for category in item.data],
                "tasks": [task.value for task in item.tasks],
            }
            for item in routes()
        ],
    }

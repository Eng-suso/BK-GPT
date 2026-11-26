"""Dove escono i dati: il registro, la regola e chi non la puo' aggirare.

SEC-06 / gate G3 del riferimento di sicurezza: ogni invio verso un fornitore
esterno e' inventariato e passa da una policy. Questi test tengono insieme tre
cose che prima vivevano separate - l'elenco dei compiti del gateway, gli host a
cui i client si collegano davvero, e il documento dei fornitori - cosi' il
prossimo LLM aggiunto alla pipeline non puo' entrare senza comparire in tutti e tre.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.llm import egress
from backend.llm.egress import DataCategory, Destination, EgressBlocked
from backend.llm.tasks import LlmTask
from backend.settings import settings

pytestmark = pytest.mark.smoke

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_DOC = ROOT / "docs" / "compliance" / "fornitori-e-invii-dati.md"


@pytest.fixture()
def prod(monkeypatch):
    monkeypatch.setattr(settings, "delir_environment", "prod")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "openai_base_url", None)
    monkeypatch.setattr(settings, "mem0_database_url", None)
    monkeypatch.setattr(settings, "tavily_api_key", None)
    monkeypatch.setattr(settings, "langsmith_tracing", False)
    monkeypatch.setattr("backend.llm.egress.langsmith_tracing_enabled", lambda: False)
    monkeypatch.setattr(settings, "docling_serve_url", "http://docling:5001")
    monkeypatch.setattr(settings, "prosimos_base_url", "http://prosimos:5000")
    monkeypatch.setattr(settings, "delir_egress_allowed_hosts", "")


class TestIlRegistro:
    def test_ogni_compito_del_gateway_ha_una_destinazione(self):
        """Un compito nuovo che nessuno ha inventariato e' un invio non dichiarato."""
        dichiarati = [task for item in egress.routes() for task in item.tasks]

        assert sorted(dichiarati) == sorted(LlmTask)
        assert len(dichiarati) == len(set(dichiarati))

    def test_la_chat_segue_l_endpoint_configurato_embedding_e_trascrizione_no(self, monkeypatch):
        """E' il caso che una lettura del codice non vedeva: con la chat su un
        altro fornitore, i vettori e l'audio continuano ad andare a OpenAI."""
        monkeypatch.setattr(settings, "openai_base_url", "https://generativelanguage.googleapis.com/v1beta/openai/")

        assert egress.route(Destination.LLM_CHAT).host == "generativelanguage.googleapis.com"
        assert egress.route(Destination.LLM_EMBEDDING).host == "api.openai.com"
        assert egress.route(Destination.TRANSCRIPTION).host == "api.openai.com"
        assert egress.route(Destination.TRANSCRIPTION_LIVE).host == "api.openai.com"

    def test_i_compiti_di_mem0_stanno_sulle_destinazioni_di_mem0(self, monkeypatch):
        """Mem0 ha i suoi client: con la chat su un altro fornitore, i suoi compiti
        non devono comparire sotto `llm_chat` ne' seguirne l'host."""
        monkeypatch.setattr(settings, "openai_base_url", "https://generativelanguage.googleapis.com/v1beta/openai/")

        chat = egress.route(Destination.LLM_CHAT).tasks
        assert LlmTask.MEMORY_EXTRACTION not in chat
        assert LlmTask.MEMORY_EMBEDDING not in chat
        assert egress.route(Destination.MEMORY_EXTRACTION).tasks == (LlmTask.MEMORY_EXTRACTION,)
        assert egress.route(Destination.MEMORY_EMBEDDING).tasks == (LlmTask.MEMORY_EMBEDDING,)

    def test_audio_e_contenuti_del_cliente_sono_dichiarati(self):
        assert DataCategory.AUDIO in egress.route(Destination.TRANSCRIPTION).data
        assert DataCategory.PROMPT_TRACE in egress.route(Destination.TRACING).data
        assert DataCategory.CUSTOMER_CONTENT in egress.route(Destination.LLM_CHAT).data

    @pytest.mark.parametrize(
        ("host", "interno"),
        [
            ("127.0.0.1", True),
            ("localhost", True),
            ("docling", True),
            ("10.0.3.4", True),
            ("::1", True),
            ("api.openai.com", False),
            ("docling.example.com", False),
            ("8.8.8.8", False),
            ("", False),
        ],
    )
    def test_cosa_e_interno(self, host, interno):
        assert egress.is_internal_host(host) is interno

    def test_l_inventario_non_espone_chiavi(self, monkeypatch):
        monkeypatch.setattr(settings, "openai_api_key", "sk-segretissima")
        monkeypatch.setattr(settings, "openai_base_url", "https://utente:pw@llm.example.com/v1")

        testo = repr(egress.inventory())

        assert "sk-segretissima" not in testo
        assert "pw" not in testo
        assert "llm.example.com" in testo


class TestLaRegola:
    def test_in_sviluppo_una_lista_vuota_permette_tutto(self, monkeypatch):
        monkeypatch.setattr(settings, "delir_environment", "dev")
        monkeypatch.setattr(settings, "delir_egress_allowed_hosts", "")

        assert egress.require(Destination.LLM_CHAT).host == "api.openai.com"

    def test_in_sviluppo_una_lista_non_vuota_vale_gia(self, monkeypatch):
        """Cosi' la regola si prova prima del deploy, non il giorno del deploy."""
        monkeypatch.setattr(settings, "delir_environment", "dev")
        monkeypatch.setattr(settings, "delir_egress_allowed_hosts", "api.openai.com")
        monkeypatch.setattr(settings, "openai_base_url", "https://api.groq.com/openai/v1")

        with pytest.raises(EgressBlocked):
            egress.require(Destination.LLM_CHAT)
        assert egress.require(Destination.LLM_EMBEDDING).host == "api.openai.com"

    def test_in_prod_senza_lista_l_app_non_parte(self, prod):
        with pytest.raises(RuntimeError) as failure:
            egress.assert_egress_is_defensible()

        # Tutte le destinazioni bloccate in un messaggio solo, non una per avvio.
        for chiave in ("llm_chat", "llm_embedding", "transcription", "transcription_live"):
            assert chiave in str(failure.value)
        assert "DELIR_EGRESS_ALLOWED_HOSTS" in str(failure.value)

    def test_in_prod_con_i_fornitori_registrati_parte(self, prod, monkeypatch):
        monkeypatch.setattr(settings, "delir_egress_allowed_hosts", "api.openai.com")

        egress.assert_egress_is_defensible()

    def test_i_servizi_self_hosted_non_chiedono_permesso(self, prod, monkeypatch):
        monkeypatch.setattr(settings, "openai_api_key", None)

        egress.assert_egress_is_defensible()

    def test_un_lettore_documenti_esterno_e_un_invio_da_autorizzare(self, prod, monkeypatch):
        """docling legge i documenti interi: puntato fuori, li porta fuori."""
        monkeypatch.setattr(settings, "openai_api_key", None)
        monkeypatch.setattr(settings, "docling_serve_url", "https://docling.fornitore.example")

        with pytest.raises(RuntimeError, match="document_reader"):
            egress.assert_egress_is_defensible()

    def test_una_destinazione_spenta_non_blocca(self, prod, monkeypatch):
        """Tavily senza chiave non manda niente: non serve autorizzarlo."""
        monkeypatch.setattr(settings, "delir_egress_allowed_hosts", "api.openai.com")

        assert egress.route(Destination.WEB_SEARCH).active is False
        egress.assert_egress_is_defensible()


class TestNessunoLaAggira:
    def test_il_client_della_chat_rifiuta_un_host_non_autorizzato(self, prod):
        from backend.llm_config import MissingProviderKey, chat_openai_kwargs

        with pytest.raises(EgressBlocked):
            chat_openai_kwargs()
        # E' configurazione: chi intercetta la chiave mancante intercetta anche questo.
        assert issubclass(EgressBlocked, MissingProviderKey)

    def test_il_gateway_registra_il_rifiuto(self, prod, monkeypatch):
        from langchain_core.messages import HumanMessage

        from backend.llm import OperationKind, gateway, operation

        scritti: list[dict] = []
        monkeypatch.setattr(gateway, "record", lambda **kw: scritti.append(kw))

        with operation(OperationKind.PLAN_SYNTHESIS):
            with pytest.raises(EgressBlocked):
                gateway.run(task=LlmTask.PLAN_QUALITY, messages=[HumanMessage("x")])

        assert scritti[-1]["error_kind"] == "EgressBlocked"

    def test_mem0_si_spegne_invece_di_uscire(self, prod, monkeypatch):
        from backend.memory import mem0_client

        monkeypatch.setattr(settings, "mem0_database_url", "postgresql://x@127.0.0.1/mem0")
        mem0_client.get_memory.cache_clear()
        try:
            memoria = mem0_client.get_memory()
        finally:
            mem0_client.get_memory.cache_clear()

        assert isinstance(memoria, mem0_client.Mem0Disabled)
        assert "DELIR_EGRESS_ALLOWED_HOSTS" in memoria.reason

    def test_la_ricerca_web_si_spegne_invece_di_uscire(self, prod, monkeypatch):
        from backend.toolsets.web import web_research

        monkeypatch.setattr(settings, "tavily_api_key", "tvly-test")

        risposta = web_research.invoke({"query": "fornitore del cliente", "reason": "test"})

        assert "not an authorised destination" in risposta

    def test_nessun_client_sdk_fuori_dai_punti_registrati(self):
        """Ogni client verso un fornitore si costruisce in un punto che chiede
        il permesso a `egress.require`. Un modulo nuovo che costruisce un client
        da solo e' un invio che l'inventario non vede."""
        costruttori = {"OpenAI", "AsyncOpenAI", "ChatOpenAI", "TavilySearch", "MemoryClient"}
        permessi = {
            "backend/llm/gateway.py",
            "backend/llm_config.py",
            "backend/llm/chat_client.py",
            "backend/toolsets/web.py",
        }
        trovati: set[str] = set()
        for path in (ROOT / "backend").rglob("*.py"):
            albero = ast.parse(path.read_text(encoding="utf-8"))
            for nodo in ast.walk(albero):
                if isinstance(nodo, ast.Call):
                    nome = getattr(nodo.func, "id", None) or getattr(nodo.func, "attr", None)
                    if nome in costruttori:
                        trovati.add(path.relative_to(ROOT).as_posix())

        assert trovati <= permessi, f"client costruiti fuori dal registro: {sorted(trovati - permessi)}"

    def test_l_url_realtime_viene_dal_registro(self):
        sorgente = (ROOT / "backend" / "api" / "routes" / "audio.py").read_text(encoding="utf-8")

        assert "wss://" not in sorgente
        assert "Destination.TRANSCRIPTION_LIVE" in sorgente


class TestIlDocumentoDeiFornitori:
    def test_ogni_destinazione_e_nel_documento(self):
        """Il documento si legge in un DPA; il registro e' quello che gira. Una
        destinazione nel codice e non nel documento e' un fornitore non dichiarato."""
        testo = INVENTORY_DOC.read_text(encoding="utf-8")

        mancanti = [item.value for item in Destination if f"`{item.value}`" not in testo]
        assert not mancanti, f"destinazioni non documentate: {mancanti}"

    def test_ogni_compito_e_nel_documento(self):
        testo = INVENTORY_DOC.read_text(encoding="utf-8")

        mancanti = [task.value for task in LlmTask if f"`{task.value}`" not in testo]
        assert not mancanti, f"compiti non documentati: {mancanti}"

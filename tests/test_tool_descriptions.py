"""Il docstring di un `@tool` e' un prompt, e va difeso come tale.

LangChain manda il docstring al modello come `description` del tool: e' il testo
su cui l'agente decide se chiamarlo e cosa non fare dopo averlo chiamato. Non e'
documentazione dell'API Python, e trattarlo come tale costa due volte.

Costa una volta perche' le istruzioni spariscono. `create_project_process`
diceva "does not start discovery, does not ask discovery questions, does not
infer missing process knowledge... Ownership moves to Process Macro only after
the record exists": erano la guardrail contro PROJECT-03. Riscritto in formato
`Args:/Returns:/Raises:`, di quelle frasi non restava niente.

Costa due volte perche' il boilerplate occupa contesto a ogni turno. Prima del
ripristino il 41% del testo di tutte le descrizioni era fatto di sezioni
`Args:/Returns:/Raises:` - fino al 64% nel subagent di setup - e i tipi elencati
li' il modello li ha gia' nello schema degli argomenti. Ridondanza pagata su
ogni chiamata.

Questi test non giudicano lo stile della prosa: verificano che il testo che il
modello legge sia scritto per il modello.
"""

from __future__ import annotations

import pytest

from backend.graphs.consulting.subgraphs.clients import clients_tools
from backend.graphs.consulting.subgraphs.home import home_tools
from backend.graphs.consulting.subgraphs.setup import setup_tools
from backend.graphs.process.subgraphs.discovery.tools import discovery_tools
from backend.graphs.process.subgraphs.evidence.tools import evidence_tools
from backend.graphs.process.subgraphs.modeling.tools import modeling_tools
from backend.graphs.project.subgraphs.delivery.tools import delivery_tools
from backend.graphs.project.subgraphs.process_coordination import process_coordination_tools
from backend.toolsets.registry import tools_by_scope


# Le sezioni di una docstring in stile API. Per un tool sono rumore: il modello
# riceve gia' tipi e obbligatorieta' dallo schema degli argomenti.
API_DOC_SECTIONS = ("Args:", "Returns:", "Raises:", "Parameters:", "Yields:")

# Annotazioni pensate per chi fa code review, non per chi sceglie il tool.
REVIEW_ANNOTATIONS = (", untrusted)", "(untrusted)")


def _bound_tools() -> dict[str, object]:
    """Ogni tool che un agente puo' davvero chiamare, macro agent e subagent."""
    tools: dict[str, object] = {}
    for toolset in (
        *tools_by_scope.values(),
        clients_tools,
        home_tools,
        setup_tools,
        delivery_tools,
        process_coordination_tools,
        discovery_tools,
        evidence_tools,
        modeling_tools,
    ):
        for tool in toolset:
            tools[tool.name] = tool
    return tools


BOUND_TOOLS = _bound_tools()


@pytest.mark.parametrize("name", sorted(BOUND_TOOLS))
def test_a_tool_description_is_written_for_the_model(name: str):
    description = getattr(BOUND_TOOLS[name], "description", "") or ""

    sections = [section for section in API_DOC_SECTIONS if section in description]
    assert not sections, (
        f"{name}: la description contiene {sections}. Il docstring di un @tool e' il "
        "prompt che il modello legge, non documentazione Python: dice quando usarlo e "
        "cosa non fare dopo. I tipi arrivano gia' dallo schema degli argomenti."
    )

    annotations = [note for note in REVIEW_ANNOTATIONS if note in description]
    assert not annotations, (
        f"{name}: la description contiene {annotations}, un'annotazione per la review "
        "che al modello non dice niente."
    )


def test_every_bound_tool_actually_has_a_description():
    """Un tool senza description e' un tool che il modello sceglie a caso."""
    empty = sorted(
        name
        for name, tool in BOUND_TOOLS.items()
        if len((getattr(tool, "description", "") or "").strip()) < 40
    )
    assert not empty, f"Tool senza una description utile: {empty}"

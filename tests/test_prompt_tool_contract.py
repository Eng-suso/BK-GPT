"""Un tool nominato in un prompt deve essere un tool che quello scope ha.

PROJECT-05 ha stabilito la regola per l'interfaccia: non inventare pulsanti,
perche' il consulente li cerca. Lo stesso vale un livello sotto, dove il costo
e' piu' alto: se il prompt dice all'agente di usare `update_workspace_project`
e quel tool non e' fra quelli bindati per lo scope, l'agente non ha modo di
obbedire. O tenta una chiamata che non esiste, o annuncia di aver salvato
qualcosa che nessuno ha scritto - e il consulente lo scopre il giorno dopo,
riaprendo un record vuoto.

Era esattamente il caso: `update_workspace_project` viveva in
`workspace_mutation_tools`, che nessun grafo binda; l'unico consumatore era la
lista piatta `tools` marcata "compatibility export". Il prompt lo nominava
comunque, in tre punti.

Il test non giudica quale tool serva a quale scope: legge i prompt reali,
cerca i nomi dei tool che il progetto conosce e verifica che ognuno sia
raggiungibile da li'. E' una domanda che il runtime puo' rispondere da solo.
"""

from __future__ import annotations

import importlib
import pkgutil
import re

import pytest

import backend
from backend.agents.primary_scope import build_scope_system_prompt
from backend.graphs.consulting.graph import CONSULTING_SUBGRAPH_CONTRACT
from backend.graphs.consulting.subgraphs.clients import clients_tools
from backend.graphs.consulting.subgraphs.home import home_tools
from backend.graphs.consulting.subgraphs.setup import setup_tools
from backend.graphs.process.graph import PROCESS_SUBGRAPH_CONTRACT
from backend.graphs.process.subgraphs.discovery.tools import discovery_tools
from backend.graphs.process.subgraphs.evidence.tools import evidence_tools
from backend.graphs.process.subgraphs.modeling.tools import modeling_tools
from backend.graphs.project.graph import PROJECT_SUBGRAPH_CONTRACT
from backend.graphs.project.subgraphs.delivery.tools import delivery_tools
from backend.graphs.project.subgraphs.process_coordination import process_coordination_tools
from backend.toolsets.registry import tools_by_scope


def _every_tool_name_the_project_defines() -> set[str]:
    """Tutti i nomi di tool che esistono nel codice, bindati o no.

    Serve come vocabolario per la ricerca nei prompt: cercare "una parola che
    sembra un tool" darebbe falsi positivi, cercare i nomi veri no.

    Un modulo che non importa non viene ignorato. Ingoiare l'errore
    rimpicciolirebbe il vocabolario in silenzio, e l'assert dello scope
    passerebbe perche' il nome che avrebbe dovuto trovare non c'e' piu': un test
    verde che non ha guardato niente. Se un modulo si rompe, questo test lo dice.
    """
    names: set[str] = set()
    broken: list[str] = []

    for module_info in pkgutil.walk_packages(backend.__path__, "backend."):
        try:
            module = importlib.import_module(module_info.name)
        except Exception as error:
            broken.append(f"{module_info.name}: {type(error).__name__}: {error}")
            continue
        for attribute in dir(module):
            if not attribute.endswith("_tools"):
                continue
            value = getattr(module, attribute)
            if isinstance(value, list) and value and hasattr(value[0], "name"):
                names |= {tool.name for tool in value}

    assert not broken, (
        "Moduli backend non importabili: il vocabolario dei tool sarebbe "
        "incompleto e il contratto verrebbe verificato contro un elenco "
        "monco.\n  " + "\n  ".join(broken)
    )
    return names


# Cosa un agente puo' davvero chiamare, per scope: i tool del macro agent piu'
# quelli dei subgraph a cui il router puo' instradare nello stesso turno.
REACHABLE_TOOLS = {
    "consultant": [*tools_by_scope["consultant"], *clients_tools, *home_tools, *setup_tools],
    "project": [*tools_by_scope["project"], *delivery_tools, *process_coordination_tools],
    "process": [*tools_by_scope["process"], *discovery_tools, *evidence_tools, *modeling_tools],
    "canvas": [*tools_by_scope["canvas"]],
}

# Uno stato minimo per scope, scelto per far uscire i rami che nominano tool:
# il progetto senza obiettivo e senza processi e' il caso in cui il prompt
# indica cosa fare, quindi e' il caso che nomina di piu'.
SCOPE_STATES = {
    "consultant": {"scope_type": "consultant"},
    "project": {"scope_type": "project", "project_id": "p-1", "project_processes": []},
    "process": {"scope_type": "process", "project_id": "p-1", "process_id": "proc-1"},
    "canvas": {"scope_type": "canvas", "project_id": "p-1", "bpmn_model_id": "m-1"},
}

SCOPE_CONTRACTS = {
    "consultant": CONSULTING_SUBGRAPH_CONTRACT,
    "project": PROJECT_SUBGRAPH_CONTRACT,
    "process": PROCESS_SUBGRAPH_CONTRACT,
    "canvas": "",
}


def _prompt_text(scope: str) -> str:
    """Tutto il testo che l'agente di uno scope legge come istruzione.

    Il contratto del subgraph include gia' la tool policy e le skill markdown
    caricate da `load_markdown_skills`, quindi una regola scritta in una skill
    conta quanto una scritta nel prompt.
    """
    return f"{build_scope_system_prompt(SCOPE_STATES[scope])}\n{SCOPE_CONTRACTS[scope]}"


@pytest.mark.parametrize("scope", sorted(REACHABLE_TOOLS))
def test_every_tool_named_in_a_prompt_is_bound_in_that_scope(scope: str):
    universe = _every_tool_name_the_project_defines()
    reachable = {tool.name for tool in REACHABLE_TOOLS[scope]}
    text = _prompt_text(scope)

    named = {name for name in universe if re.search(rf"\b{re.escape(name)}\b", text)}
    unreachable = sorted(named - reachable)

    assert not unreachable, (
        f"Lo scope {scope} nomina tool che non puo' chiamare: {unreachable}. "
        "O si bindano nello scope, o il prompt smette di prometterli."
    )


def test_the_project_can_write_the_record_its_prompt_talks_about():
    """PROJECT-01 si chiude solo se l'obiettivo si puo' anche correggere.

    Scriverlo alla creazione non basta: `create_initial_workspace_setup` passa
    una volta sola, e un incarico il cui mandato cambia non ha altra strada.
    """
    assert "update_workspace_project" in {tool.name for tool in tools_by_scope["project"]}


def test_the_process_can_move_its_own_record():
    assert "update_workspace_process" in {tool.name for tool in tools_by_scope["process"]}


def test_the_objective_hint_only_names_the_tool_where_it_exists():
    """Ogni scope sotto un progetto porta il `project_id`, non il tool."""
    project = build_scope_system_prompt(SCOPE_STATES["project"])
    process = build_scope_system_prompt(SCOPE_STATES["process"])

    assert "update_workspace_project" in project
    assert "update_workspace_project" not in process
    # Il fatto resta visibile: manca il mandato, e si sa dove si registra.
    assert "project_objective: non registrato" in process

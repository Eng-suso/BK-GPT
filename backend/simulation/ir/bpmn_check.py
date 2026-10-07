"""Un IR e il BPMN che deve simulare parlano degli stessi elementi?

Il modello si valida da solo (riferimenti interni, probabilita', calendari), ma
non sa quale BPMN girera'. Un'attivita' con un id che il diagramma non ha
verrebbe ignorata dal motore; un task senza parametri farebbe fallire il run
dopo minuti di coda. Qui si rifiuta prima, con l'elenco di cio' che non torna.
"""

from __future__ import annotations

from backend.simulation.ir.model import SimulationModel
from backend.simulation.models import BpmnGateway, BpmnTask


def check_model_against_bpmn(
    model: SimulationModel,
    tasks: list[BpmnTask],
    gateways: list[BpmnGateway],
) -> None:
    """Solleva ``ValueError`` con tutti i disallineamenti fra modello e BPMN."""
    problems: list[str] = []
    task_ids = {task.id for task in tasks}
    activity_ids = {activity.element_id for activity in model.activities}
    problems += _listed("attivita' che il BPMN non ha", activity_ids - task_ids)
    problems += _listed("task del BPMN senza parametri", task_ids - activity_ids)

    flows_by_gateway = {gateway.id: {flow.id for flow in gateway.outgoing_flows} for gateway in gateways}
    configured = {gateway.element_id: gateway for gateway in model.gateways}
    problems += _listed("gateway che il BPMN non ha", set(configured) - set(flows_by_gateway))
    problems += _listed("gateway del BPMN senza rami", set(flows_by_gateway) - set(configured))
    for gateway_id in sorted(set(configured) & set(flows_by_gateway)):
        branches = {branch.flow_id for branch in configured[gateway_id].branches}
        expected = flows_by_gateway[gateway_id]
        problems += _listed(f"gateway {gateway_id}: rami che il BPMN non ha", branches - expected)
        problems += _listed(f"gateway {gateway_id}: uscite senza ramo", expected - branches)

    updated = {update.element_id for update in model.attribute_updates}
    problems += _listed("aggiornamenti di attributi su elementi che il BPMN non ha", updated - task_ids)

    if problems:
        raise ValueError("Il modello non corrisponde al BPMN: " + "; ".join(problems) + ".")


def _listed(what: str, ids: set[str]) -> list[str]:
    return [f"{what}: {', '.join(sorted(ids))}"] if ids else []

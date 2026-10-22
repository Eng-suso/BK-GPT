"""SIM-11e: un sottoprocesso semplice si srotola nel processo che lo contiene.

Prima ogni sottoprocesso diventava un'unica attivita' (scatola nera): i passi
interni non avevano durate, risorse ne' rami propri. Ora, se ha un solo inizio
e una sola fine senza eventi, un flusso che entra e uno che esce, nessun evento
di bordo e nessun ciclo, i suoi passi sono passi del processo.
"""

import pytest

from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.compatibility import bpmn_compatibility_report
from backend.simulation.scenario_builder import describe_scenario_template

_NS = 'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"'


def _bpmn(*, sub_extra: str = "", inner: str | None = None, process_extra: str = "", lane: bool = False) -> str:
    inner = inner if inner is not None else """
      <bpmn:startEvent id="SP_s" />
      <bpmn:task id="SP_check" name="Verifica" />
      <bpmn:exclusiveGateway id="SP_g" />
      <bpmn:task id="SP_ok" name="Approva" />
      <bpmn:task id="SP_ko" name="Rifiuta" />
      <bpmn:exclusiveGateway id="SP_j" />
      <bpmn:endEvent id="SP_e" />
      <bpmn:sequenceFlow id="SP_f1" sourceRef="SP_s" targetRef="SP_check" />
      <bpmn:sequenceFlow id="SP_f2" sourceRef="SP_check" targetRef="SP_g" />
      <bpmn:sequenceFlow id="SP_ok_f" sourceRef="SP_g" targetRef="SP_ok" />
      <bpmn:sequenceFlow id="SP_ko_f" sourceRef="SP_g" targetRef="SP_ko" />
      <bpmn:sequenceFlow id="SP_f3" sourceRef="SP_ok" targetRef="SP_j" />
      <bpmn:sequenceFlow id="SP_f4" sourceRef="SP_ko" targetRef="SP_j" />
      <bpmn:sequenceFlow id="SP_f5" sourceRef="SP_j" targetRef="SP_e" />"""
    lanes = """<bpmn:laneSet id="LS"><bpmn:lane id="L_back" name="Back office">
      <bpmn:flowNodeRef>SP</bpmn:flowNodeRef></bpmn:lane>
      <bpmn:lane id="L_front" name="Sportello"><bpmn:flowNodeRef>A</bpmn:flowNodeRef><bpmn:flowNodeRef>B</bpmn:flowNodeRef></bpmn:lane></bpmn:laneSet>""" if lane else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions {_NS} id="D">
  <bpmn:process id="P" isExecutable="false">{lanes}
    <bpmn:startEvent id="S" /><bpmn:task id="A" name="Ricevi" />
    <bpmn:subProcess id="SP" name="Istruttoria">{sub_extra}{inner}
    </bpmn:subProcess>
    <bpmn:task id="B" name="Comunica" /><bpmn:endEvent id="E" />
    <bpmn:sequenceFlow id="f1" sourceRef="S" targetRef="A" /><bpmn:sequenceFlow id="f2" sourceRef="A" targetRef="SP" />
    <bpmn:sequenceFlow id="f3" sourceRef="SP" targetRef="B" /><bpmn:sequenceFlow id="f4" sourceRef="B" targetRef="E" />
    {process_extra}
  </bpmn:process>
</bpmn:definitions>"""


def test_a_simple_subprocess_becomes_steps_of_the_process():
    template = describe_scenario_template(normalize_bpmn_for_prosimos(_bpmn()))

    assert [t.element_id for t in template.tasks] == ["A", "SP_check", "SP_ok", "SP_ko", "B"]
    assert [(g.element_id, [b.flow_id for b in g.branches]) for g in template.gateways] == [("SP_g", ["SP_ok_f", "SP_ko_f"])]
    normalized = normalize_bpmn_for_prosimos(_bpmn())
    assert 'id="SP"' not in normalized and 'id="SP_s"' not in normalized and 'id="SP_e"' not in normalized
    assert 'sourceRef="A" targetRef="SP_check"' in normalized
    assert 'sourceRef="SP_j" targetRef="B"' in normalized


def test_a_subprocess_inside_a_subprocess_unrolls_too():
    nested = """
      <bpmn:startEvent id="SP_s" />
      <bpmn:subProcess id="SP2" name="Controlli">
        <bpmn:startEvent id="SP2_s" /><bpmn:task id="SP2_t" name="Controlla firme" /><bpmn:endEvent id="SP2_e" />
        <bpmn:sequenceFlow id="SP2_f1" sourceRef="SP2_s" targetRef="SP2_t" />
        <bpmn:sequenceFlow id="SP2_f2" sourceRef="SP2_t" targetRef="SP2_e" />
      </bpmn:subProcess>
      <bpmn:endEvent id="SP_e" />
      <bpmn:sequenceFlow id="SP_f1" sourceRef="SP_s" targetRef="SP2" />
      <bpmn:sequenceFlow id="SP_f2" sourceRef="SP2" targetRef="SP_e" />"""
    template = describe_scenario_template(normalize_bpmn_for_prosimos(_bpmn(inner=nested)))

    assert [t.element_id for t in template.tasks] == ["A", "SP2_t", "B"]


@pytest.mark.parametrize(("bpmn", "why"), [
    (_bpmn(sub_extra="<bpmn:multiInstanceLoopCharacteristics />"), "multi-istanza"),
    (_bpmn(process_extra='<bpmn:boundaryEvent id="BE" attachedToRef="SP"><bpmn:errorEventDefinition /></bpmn:boundaryEvent>'), "evento di bordo"),
    (_bpmn(inner="""<bpmn:startEvent id="SP_s"><bpmn:messageEventDefinition /></bpmn:startEvent><bpmn:task id="SP_t" name="X" />
      <bpmn:endEvent id="SP_e" /><bpmn:sequenceFlow id="i1" sourceRef="SP_s" targetRef="SP_t" /><bpmn:sequenceFlow id="i2" sourceRef="SP_t" targetRef="SP_e" />"""), "inizio a messaggio"),
], ids=lambda value: value if isinstance(value, str) and len(value) < 30 else "")
def test_other_subprocesses_stay_a_black_box(bpmn, why):
    template = describe_scenario_template(normalize_bpmn_for_prosimos(bpmn))
    report = {e.element_id: e for e in bpmn_compatibility_report(bpmn).elements}

    assert "SP" in [t.element_id for t in template.tasks], why
    assert report["SP"].status == "flattened", why


def test_the_report_says_the_subprocess_is_simulated_step_by_step():
    report = {e.element_id: e for e in bpmn_compatibility_report(_bpmn()).elements}

    assert (report["SP"].status, report["SP"].simulated_as) == ("preserved", "expanded")
    assert (report["SP_check"].status, report["SP_check"].parent_id) == ("preserved", "SP")
    assert (report["SP_s"].status, report["SP_s"].impact) == ("approximated", "none")
    # Il flusso che entrava nel sottoprocesso entra nel suo primo passo; quello che ne usciva parte dall'ultimo.
    assert (report["f2"].status, report["f2"].simulated_as) == ("approximated", "A → SP_check")
    assert (report["f3"].status, report["f3"].simulated_as) == ("approximated", "SP_j → B")


def test_the_steps_belong_to_the_lane_of_their_subprocess():
    bpmn = _bpmn(lane=True)
    template = describe_scenario_template(normalize_bpmn_for_prosimos(bpmn), source_bpmn_xml=bpmn)

    lanes = {r.name: sorted(r.task_ids) for r in template.resources}
    assert lanes == {"Back office": ["SP_check", "SP_ko", "SP_ok"], "Sportello": ["A", "B"]}

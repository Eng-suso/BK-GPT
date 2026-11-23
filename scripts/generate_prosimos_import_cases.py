"""Genera tests/fixtures/simulation/prosimos_import_cases.json (atteso calcolato dal gemello Python)."""
import copy, json
from pathlib import Path
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.scenario_builder import describe_scenario_template
from backend.simulation.prosimos_import import import_prosimos_json, ProsimosImportError

NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMN = f'''<definitions xmlns="{NS}" id="D"><process id="P" isExecutable="false">
<startEvent id="S"/><task id="T1" name="Ricevi"/><exclusiveGateway id="G1" name="Importo?"/>
<task id="T2" name="Approva"/><task id="T3" name="Archivia"/><exclusiveGateway id="GJ"/>
<intermediateCatchEvent id="W1" name="Attesa fornitore"><timerEventDefinition/></intermediateCatchEvent><endEvent id="E"/>
<sequenceFlow id="f1" sourceRef="S" targetRef="T1"/><sequenceFlow id="f2" sourceRef="T1" targetRef="G1"/>
<sequenceFlow id="f3" sourceRef="G1" targetRef="T2"/><sequenceFlow id="f4" sourceRef="G1" targetRef="T3"/>
<sequenceFlow id="f5" sourceRef="T2" targetRef="GJ"/><sequenceFlow id="f6" sourceRef="T3" targetRef="GJ"/>
<sequenceFlow id="f7" sourceRef="GJ" targetRef="W1"/><sequenceFlow id="f8" sourceRef="W1" targetRef="E"/>
</process></definitions>'''
template = describe_scenario_template(normalize_bpmn_for_prosimos(BPMN), source_bpmn_xml=BPMN)
cal = lambda i, p: {"id": i, "name": i, "time_periods": p}
weekdays = [{"from": "MONDAY", "to": "FRIDAY", "beginTime": "09:00:00", "endTime": "17:00:00"}]
d = lambda n, *v: {"distribution_name": n, "distribution_params": [{"value": x} for x in v]}
BASE = {
    "resource_profiles": [{"id": "clerks", "name": "Clerks", "resource_list": [
        {"id": "clerk", "name": "Clerk", "cost_per_hour": 30, "amount": 2, "calendar": "shift"},
        {"id": "bot", "name": "Bot", "cost_per_hour": 0, "amount": 1, "calendar": "always"}]}],
    "resource_calendars": [cal("shift", weekdays), cal("always", [{"from": "MONDAY", "to": "SUNDAY", "beginTime": "00:00:00", "endTime": "23:59:59.999000"}])],
    "task_resource_distribution": [
        {"task_id": "T1", "resources": [{"resource_id": "clerk", **d("norm", 600, 60, 300, 900)}, {"resource_id": "bot", **d("fix", 0)}]},
        {"task_id": "T2", "resources": [{"resource_id": "clerk", **d("lognorm", 1200, 14400, 600, 3600)}]},
        {"task_id": "T3", "resources": [{"resource_id": "bot", **d("expon", 120, 60, 600)}]},
    ],
    "gateway_branching_probabilities": [{"gateway_id": "G1", "probabilities": [{"path_id": "f3", "value": "0.3"}, {"path_id": "f4", "value": "0.7"}]}],
    "arrival_time_distribution": d("gamma", 900, 90000, 60, 7200),
    "arrival_time_calendar": weekdays,
    "event_distribution": [{"event_id": "W1", **d("uniform", 3600, 7200)}],
}
cases = []
def case(name, source, mapping=None, current=None):
    entry = {"name": name, "source": source, "mapping": mapping or {}, "current": current}
    try:
        result = import_prosimos_json(source, current, template, mapping)
        entry["expected"] = {"draft": result.draft, "warnings": result.warnings}
    except ProsimosImportError as exc:
        entry["error"] = str(exc)
    cases.append(entry)

case("tutte le sezioni di base", BASE)
simod = copy.deepcopy(BASE)
simod.update({"process_model": "C:/simod/best.bpmn", "model_type": "CRISP", "granule_size": {"value": 15, "time_unit": "MINUTES"}})
simod["gateway_branching_probabilities"].append({"gateway_id": "GJ", "probabilities": [{"path_id": "f7", "value": 1}]})
simod["resource_profiles"][0]["resource_list"][0]["assignedTasks"] = ["T1", "T2"]
simod["resource_profiles"][0]["resource_list"][1]["skills"] = ["ocr"]
case("scenario SIMOD: metadati, join, microsecondi, campi in piu'", simod)
extra = copy.deepcopy(BASE)
extra.update({"batch_processing": [{"task_id": "T2", "type": "Sequential", "size_distrib": []}], "case_attributes": [{"name": "importo", "type": "continuous", "values": d("norm", 1000, 100, 0, 5000)}], "branch_rules": [], "multitask": {"type": "local"}})
case("sezioni non ancora rappresentate: importate le altre, dichiarate queste", extra)
skew = copy.deepcopy(BASE)
skew["gateway_branching_probabilities"][0]["probabilities"] = [{"path_id": "f3", "value": 3}, {"path_id": "f4", "value": 1}]
case("probabilita' che non sommano a 1: normalizzate con avviso", skew)
mapped = copy.deepcopy(BASE)
mapped["task_resource_distribution"][0]["task_id"] = "Activity_OLD"
mapped["gateway_branching_probabilities"][0] = {"gateway_id": "G_OLD", "probabilities": [{"path_id": "old_a", "value": 0.4}, {"path_id": "old_b", "value": 0.6}]}
case("riferimenti di un altro BPMN rimappati", mapped, mapping={"tasks": {"Activity_OLD": "T1"}, "gateways": {"G_OLD": "G1"}, "flows": {"G_OLD::old_a": "f3", "G_OLD::old_b": "f4"}})
current = {"scenarioName": "Pratiche Q3", "totalCases": 500, "arrivalIntervalMinutes": 10, "defaultTaskMinutes": 5, "resources": [], "tasks": {}, "gateways": {}, "seed": 42}
case("la bozza corrente conserva nome, casi e seed", BASE, current=current)
bad = copy.deepcopy(BASE); bad["task_resource_distribution"][2]["resources"][0] = {"resource_id": "bot", **d("triang", 1, 2, 3)}
case("errore: distribuzione che il motore non ha", bad)
bad = copy.deepcopy(BASE); bad["task_resource_distribution"].pop()
case("errore: attivita' del BPMN senza durata", bad)
bad = copy.deepcopy(BASE); bad["gateway_branching_probabilities"].append({"gateway_id": "G_X", "probabilities": [{"path_id": "a", "value": 0.5}, {"path_id": "b", "value": 0.5}]})
case("errore: decisione vera assente dal BPMN", bad)
bad = copy.deepcopy(BASE); bad["gateway_branching_probabilities"][0]["probabilities"][0]["value"] = -0.3
case("errore: probabilita' negativa", bad)
bad = copy.deepcopy(BASE); bad["resource_profiles"][0]["resource_list"][0]["calendar"] = "missing"
case("errore: calendario risorsa inesistente", bad)

out = {"_doc": "Casi condivisi da backend/simulation/prosimos_import.py e frontend prosimosJson.ts. Rigenerare con lo script descritto nel test Python.",
       "template": template.model_dump(mode="json"), "cases": cases}
Path("tests/fixtures/simulation/prosimos_import_cases.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for c in cases: print(c["name"], "->", "ERR " + c["error"] if "error" in c else [w["kind"] + ":" + w["target"] for w in c["expected"]["warnings"]])

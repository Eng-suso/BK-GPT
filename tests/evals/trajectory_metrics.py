"""La traiettoria dell'agente: quali tool chiama, con quali argomenti, in che ordine.

Una risposta giusta puo' nascere da un percorso sbagliato: l'agente che dice da
dove viene un'affermazione riassumendo a memoria, invece di leggere la
provenance, oggi azzecca e domani inventa. Qui si guarda il percorso, non la
risposta.

Una traiettoria attesa non e' un'opinione: ogni regola cita la frase del prodotto
(prompt, docstring di un tool, policy) che la impone, e un test L0 verifica che
quella frase ci sia ancora.

| metrica | cosa misura |
| --- | --- |
| tool selection accuracy | quota di compiti in cui l'agente chiama tutto cio' che deve e niente di vietato |
| forbidden rate | quota di compiti con almeno una chiamata vietata |
| redundant call rate | quota di chiamate identiche (stesso tool, stessi argomenti) a una gia' fatta |
| over budget rate | quota di compiti oltre il numero massimo di chiamate |
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]

    def key(self) -> str:
        return f"{self.name}:{json.dumps(self.args, sort_keys=True, ensure_ascii=False, default=str)}"


def tool_calls(messages: list[Any]) -> list[ToolCall]:
    """Le chiamate ai tool di un turno, nell'ordine in cui l'agente le ha chieste.

    Accetta i messaggi LangChain (`AIMessage.tool_calls`) e la loro forma
    serializzata (dict con `tool_calls`).
    """
    calls: list[ToolCall] = []
    for message in messages:
        raw = message.get("tool_calls") if isinstance(message, dict) else getattr(message, "tool_calls", None)
        for call in raw or []:
            calls.append(ToolCall(name=str(call["name"]), args=dict(call.get("args") or {})))
    return calls


@dataclass(frozen=True)
class CallRule:
    """Un tool, e facoltativamente i valori ammessi per alcuni argomenti."""

    tool: str
    args: dict[str, list[Any]] = field(default_factory=dict)

    def matches(self, call: ToolCall) -> bool:
        if call.name != self.tool:
            return False
        return all(str(call.args.get(name, "")).strip().lower() in {str(v).lower() for v in allowed}
                   for name, allowed in self.args.items())

    def describe(self) -> str:
        if not self.args:
            return self.tool
        constraints = ", ".join(f"{name} in {allowed}" for name, allowed in self.args.items())
        return f"{self.tool}({constraints})"


@dataclass(frozen=True)
class ExpectedTrajectory:
    id: str
    agent: str
    request: str
    rule: str
    rule_source: str
    must_call: list[CallRule]
    must_not_call: list[CallRule]
    max_tool_calls: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExpectedTrajectory":
        def rules(items: list[dict[str, Any]]) -> list[CallRule]:
            return [CallRule(tool=item["tool"], args=dict(item.get("args") or {})) for item in items]

        return cls(
            id=data["id"],
            agent=data["agent"],
            request=data["request"],
            rule=data["rule"],
            rule_source=data["rule_source"],
            must_call=rules(data.get("must_call") or []),
            must_not_call=rules(data.get("must_not_call") or []),
            max_tool_calls=int(data["max_tool_calls"]),
        )


def load_trajectories(path: Path) -> list[ExpectedTrajectory]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = [ExpectedTrajectory.from_dict(item) for item in data["tasks"]]
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("traiettorie con lo stesso id")
    return items


@dataclass
class TrajectoryResult:
    task_id: str
    calls: int
    missing: list[str]
    forbidden: list[str]
    redundant: int
    over_budget: bool

    @property
    def correct(self) -> bool:
        return not self.missing and not self.forbidden

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "correct": self.correct,
            "calls": self.calls,
            "missing": self.missing,
            "forbidden": self.forbidden,
            "redundant": self.redundant,
            "over_budget": self.over_budget,
        }


def score_trajectory(expected: ExpectedTrajectory, calls: list[ToolCall]) -> TrajectoryResult:
    seen: set[str] = set()
    redundant = 0
    for call in calls:
        if call.key() in seen:
            redundant += 1
        seen.add(call.key())
    return TrajectoryResult(
        task_id=expected.id,
        calls=len(calls),
        missing=[rule.describe() for rule in expected.must_call if not any(rule.matches(call) for call in calls)],
        forbidden=[
            rule.describe() for rule in expected.must_not_call if any(rule.matches(call) for call in calls)
        ],
        redundant=redundant,
        over_budget=len(calls) > expected.max_tool_calls,
    )


TRAJECTORY_METRICS = ("tool_selection_accuracy", "forbidden_rate", "redundant_call_rate", "over_budget_rate")


def aggregate_trajectories(results: list[TrajectoryResult]) -> dict[str, float]:
    if not results:
        return {name: 0.0 for name in TRAJECTORY_METRICS}
    count = len(results)
    total_calls = sum(result.calls for result in results)
    return {
        "tool_selection_accuracy": round(sum(result.correct for result in results) / count, 4),
        "forbidden_rate": round(sum(bool(result.forbidden) for result in results) / count, 4),
        "redundant_call_rate": round(sum(result.redundant for result in results) / total_calls, 4) if total_calls else 0.0,
        "over_budget_rate": round(sum(result.over_budget for result in results) / count, 4),
    }

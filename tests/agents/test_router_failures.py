"""Il router ripiega su "direct" solo per i guasti del provider o dell'uscita.

Un difetto nostro (un `TypeError`, un `KeyError`) non e' un guasto del modello:
assorbirlo trasformava ogni bug in una risposta "direct" senza traccia.
"""

import pytest
from langchain_core.exceptions import OutputParserException

from backend.graphs.routing_contracts import (
    ProcessRoutingDecision,
    invalid_process_decision,
    invoke_structured_router,
)
from backend.services import degradation_counters


class _FailingRunnable:
    def __init__(self, error: Exception):
        self._error = error

    def stream(self, input, config=None, **kwargs):
        raise self._error


class _FailingLlm:
    def __init__(self, error: Exception):
        self._error = error

    def with_structured_output(self, model, method):
        return _FailingRunnable(self._error)


def _route(error: Exception):
    return invoke_structured_router(
        _FailingLlm(error),
        ProcessRoutingDecision,
        [],
        {},
        invalid_process_decision,
    )


@pytest.mark.parametrize(
    "error",
    [TimeoutError("provider lento"), OutputParserException("json rotto")],
)
def test_provider_or_output_failures_fall_back_to_direct_and_are_counted(error):
    before = degradation_counters.snapshot().get("process_router:router_recovery_direct", 0)

    decision, source, reason = _route(error)

    assert source == "router_recovery_direct"
    assert decision.route == "direct"
    assert type(error).__name__ in (reason or "")
    after = degradation_counters.snapshot().get("process_router:router_recovery_direct", 0)
    assert after == before + 1


def test_our_own_defects_propagate():
    with pytest.raises(TypeError):
        _route(TypeError("argomento sbagliato"))

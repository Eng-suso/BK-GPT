from backend.graphs.consulting.graph import VALID_CONSULTING_ROUTES, parse_router_json
from backend.graphs.consulting.tools import consultant_tools
from backend.schemas.api import EvalCheckResult, EvalRunResponse
from backend.services.trace_recorder import new_trace_context


def run_observability_smoke_eval() -> EvalRunResponse:
    trace = new_trace_context(scope_type="eval", scope_key="eval:observability")
    checks = []

    parsed = parse_router_json(
        '{"route":"clients","confidence":0.7,"reason":"client operation"}',
        user_request="crea cliente ACME",
    )
    checks.append(
        EvalCheckResult(
            name="consulting_router_contract",
            status="pass" if parsed["consulting_route"] in VALID_CONSULTING_ROUTES else "fail",
            summary="Router parser returns a valid structured route.",
            details={"route": parsed["consulting_route"]},
        )
    )

    checks.append(
        EvalCheckResult(
            name="consult_macro_tool_budget",
            status="pass" if len(consultant_tools) <= 8 else "fail",
            summary="Consult Macro direct toolset stays within the 8-tool budget.",
            details={"tool_count": len(consultant_tools), "tools": [tool.name for tool in consultant_tools]},
        )
    )

    return EvalRunResponse(
        ok=all(check.status != "fail" for check in checks),
        suite="observability_smoke",
        checks=checks,
        trace_id=trace.trace_id,
    )

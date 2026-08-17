import json


def format_web_results(response, reason: str) -> str:
    return f"Ricerca web eseguita per: {reason}\n\n{response}"


def format_workspace_result(action: str, payload: dict | list[dict]) -> str:
    return f"{action}\n{json.dumps(payload, ensure_ascii=False, indent=2)}"

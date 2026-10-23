from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.agent import recent_context_messages


def test_recent_context_messages_drops_orphan_tool_messages():
    messages = [
        HumanMessage(content="prima richiesta"),
        ToolMessage(content="orphan tool result", tool_call_id="call_missing"),
        HumanMessage(content="nuova richiesta"),
    ]

    result = recent_context_messages(messages)

    assert [message.type for message in result] == ["human", "human"]
    assert all(getattr(message, "tool_call_id", None) != "call_missing" for message in result)


def test_recent_context_messages_keeps_valid_tool_call_group():
    messages = [
        HumanMessage(content="dammi overview"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "get_workspace_overview",
                    "args": {},
                }
            ],
        ),
        ToolMessage(content="Workspace overview {}", tool_call_id="call_1"),
    ]

    result = recent_context_messages(messages)

    assert [message.type for message in result] == ["human", "ai", "tool"]
    assert result[-1].tool_call_id == "call_1"


def test_recent_context_messages_does_not_cut_into_tool_group():
    messages = [
        HumanMessage(content=f"old {index}")
        for index in range(10)
    ]
    messages.extend(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call_1",
                        "name": "get_workspace_overview",
                        "args": {},
                    }
                ],
            ),
            ToolMessage(content="Workspace overview {}", tool_call_id="call_1"),
        ]
    )

    result = recent_context_messages(messages, limit=1)

    # Il gruppo resta intero; in testa c'e' l'ultima richiesta dell'utente.
    assert [message.type for message in result] == ["human", "ai", "tool"]
    assert result[0].content == "old 9"


def _tool_round(round_index: int) -> list:
    call_ids = [f"call_{round_index}_a", f"call_{round_index}_b"]
    return [
        AIMessage(
            content="",
            tool_calls=[{"id": call_id, "name": "get_workspace_overview", "args": {}} for call_id in call_ids],
        ),
        *(ToolMessage(content="Workspace overview {}", tool_call_id=call_id) for call_id in call_ids),
    ]


def test_recent_context_messages_keeps_the_request_after_many_tool_rounds():
    # Tre giri da due tool riempiono la finestra: la richiesta del turno non
    # deve uscire dal prompt, o l'agente prosegue senza sapere cosa gli e'
    # stato chiesto.
    messages = [HumanMessage(content="turno vecchio"), AIMessage(content="risposta vecchia")]
    messages.append(HumanMessage(content="richiesta del turno"))
    for round_index in range(4):
        messages.extend(_tool_round(round_index))

    result = recent_context_messages(messages)

    assert result[0].content == "richiesta del turno"
    assert all(message.content != "turno vecchio" for message in result)
    assert [message.type for message in result[-3:]] == ["ai", "tool", "tool"]


def test_recent_context_messages_keeps_the_request_beyond_the_scan_window():
    messages = [HumanMessage(content="richiesta del turno")]
    for round_index in range(10):
        messages.extend(_tool_round(round_index))

    result = recent_context_messages(messages)

    assert result[0].content == "richiesta del turno"
    assert result[1].type == "ai"

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

    assert [message.type for message in result] == ["ai", "tool"]

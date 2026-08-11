import sqlite3

from anyio import Path
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langgraph.graph import END, StateGraph, START, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.sqlite import SqliteSaver
from backend.tools import tools

from backend.settings import settings, SYSTEM_PROMPT, ALLOWED_MODELS, DEFAULT_GOOGLE_MODEL, DEFAULT_OPENAI_MODEL


SYSTEM_PROMPT = """
You are a helpful Agentic AI assistant named BK-GPT similar to ChatGPT.

You can:
1. Answer normal questions.
2. Use tools when needed.
3. Search uploaded documents using the RAG tool.
4. Search the web for latest/current information using Tavily Search.
5. Remember important user information using the memory tool.
6. Recall memory when useful.

Rules:
- If the user asks about latest news, current events, recent updates, today's information, current prices, current people, current versions, new releases, or anything time-sensitive, use Tavily Search.
- If the user asks about an uploaded document, use search_uploaded_documents.
- If the user asks you to remember something, use remember_this.
- If the user asks about previous preferences or saved facts, use recall_memory.
- When using web search, summarize clearly and mention that the answer is based on web search results.
- Be clear, helpful, and concise.
"""

#i want to save the chat in a sqlite database so that the user can continue the conversation later

def normalize_model_name(model_name: str | None) -> str:
    """
    Validate and normalize the model name.
    If missing or not allowed, fall back to the configured Google model.
    """
    if not model_name:
        return settings.google_model

    model_name = model_name.strip()

    if model_name in ALLOWED_MODELS:
        return model_name

    if model_name.startswith("gemini"):
        return settings.google_model

    return DEFAULT_OPENAI_MODEL

def build_agent(model_name:str):
    """
    Build one langgraph agent with the given model name. The agent can use tools and has a system prompt.
    """
    selected_model = normalize_model_name(model_name)

    if selected_model.startswith("gemini"):
        llm = ChatGoogleGenerativeAI(
        model=selected_model,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        timeout=settings.model_timeout_seconds,
        max_retries=settings.model_max_retries,
        streaming=True,
    )
    else:
        llm = ChatOpenAI(
        model=selected_model,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        timeout=settings.model_timeout_seconds,
        max_retries=settings.model_max_retries,
        streaming=True,
    )
    #llm tools awareness 
    llm_with_tools = llm.bind_tools(tools)

    def chatbot_node(state: MessagesState):
        # Add the system prompt to the state
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state['messages']
        
        # Generate a response using the LLM with tools
        response = llm_with_tools.stream(messages)

        return {'messages': [response]}

    # tool execution node that will execute the tools when needed

    tool_node = ToolNode(tools)


    # Create a state graph with the chatbot node and tool node

    workflow = StateGraph(MessagesState)

    workflow.add_node("chatbot", chatbot_node)
    workflow.add_node("tool_node", tool_node)

    workflow.add_edge(START, "chatbot")
    workflow.add_conditional_edges("chatbot", tools_condition)
    workflow.add_edge("tool_node", "chatbot")

    conn = sqlite3.connect('data/agent_checkpoint.db',
                           check_same_thread=False)  # Allow access from multiple threads
    
    checkpointer = SqliteSaver(conn)


    return workflow.compile(checkpointer=checkpointer)

_AGENT_CACHE ={}

def get_agent(model_name:str | None = None):
    """
    Get a cached agent for the given model name, or build a new one if not cached.
    """
    selected_model = normalize_model_name(model_name)

    if selected_model not in _AGENT_CACHE:
        _AGENT_CACHE[selected_model] = build_agent(selected_model)

    return _AGENT_CACHE[selected_model]




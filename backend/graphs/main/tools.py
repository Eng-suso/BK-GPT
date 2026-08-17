MAIN_TOOL_POLICY = """
Main agent tools.

The main graph does not own operational tools. It classifies context, loads
working memory, routes each thread to the correct scoped subgraph and then stops.
All mutations and external actions must happen inside the scoped subgraph tools.
""".strip()


main_tools = []

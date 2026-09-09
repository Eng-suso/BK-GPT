"""Agent eval: qualita' del lavoro dell'agente, non solo correttezza del codice.

Non girano per default. Chiamano l'LLM vero, costano, e il loro esito non e' un
booleano: e' un punteggio contro una rubrica deterministica.

    DELIR_AGENT_EVAL=1 uv run pytest tests/evals -q -s
"""

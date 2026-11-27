"""Un finto OpenAI (e un finto Supabase) per il test di carico, con latenze realistiche.

Il test di carico misura DeliR, non il fornitore: thread, pool del database,
checkpointer, registro dei consumi, coda delle simulazioni. Per questo il
modello risponde da qui, con i tempi di un modello vero (primo token dopo
`FAKE_TTFT_MS`, poi `FAKE_TOKENS_PER_S`) e senza spendere niente.

Risponde a:

- `POST /v1/chat/completions`, in streaming e no. Se la richiesta chiede una
  risposta strutturata (`response_format` con JSON schema, o uno strumento
  forzato) la riempie a partire dallo schema, cosi' il codice che la legge
  procede invece di fallire;
- `POST /v1/embeddings`: vettori della dimensione chiesta;
- `GET /auth/v1/.well-known/jwks.json`: la chiave pubblica con cui
  `run.py` firma i token dei dieci account (ES256, come Supabase).

    uv run python -m scripts.load_test.fake_openai --port 8099

Solo per test locali: nessuna autenticazione, nessun dato salvato.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

TTFT_S = float(os.environ.get("FAKE_TTFT_MS", "800")) / 1000
TOKENS_PER_S = float(os.environ.get("FAKE_TOKENS_PER_S", "40"))
ANSWER_TOKENS = int(os.environ.get("FAKE_ANSWER_TOKENS", "120"))
STRUCTURED_S = float(os.environ.get("FAKE_STRUCTURED_MS", "1200")) / 1000
JWKS_FILE = Path(os.environ.get("FAKE_JWKS_FILE", "/var/tmp/delir-load/jwks.json"))

app = FastAPI()
_stats = {"chat": 0, "chat_stream": 0, "structured": 0, "embeddings": 0}

_WORDS = (
    "Il processo di approvazione degli ordini passa dall'ufficio acquisti, che verifica "
    "il budget e inoltra la richiesta alla direzione quando l'importo supera la soglia. "
    "I tempi di attesa piu' lunghi stanno nella verifica del fornitore e nel secondo "
    "livello di firma, dove le pratiche restano ferme in media due giorni."
).split()


def _fill(schema: dict[str, Any], defs: dict[str, Any], depth: int = 0) -> Any:
    """Un valore che rispetta `schema`, il piu' piccolo possibile."""
    if depth > 8:
        return None
    if "default" in schema:
        # Il default dello schema e' la scelta "normale" (route="direct", nessuna
        # domanda di chiarimento): e' il percorso che un turno vero fa quasi sempre.
        return schema["default"]
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        return _fill(defs.get(name, {}), defs, depth + 1)
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            options = [o for o in schema[key] if o.get("type") != "null"] or schema[key]
            return _fill(options[0], defs, depth + 1)
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), "null")
    if kind == "object" or "properties" in schema:
        props = schema.get("properties", {})
        value = {name: _fill(sub, defs, depth + 1) for name, sub in props.items()}
        if "confidence" in value:
            value["confidence"] = 0.9  # un router sicuro, come quasi sempre
        return value
    if kind == "array":
        minimum = schema.get("minItems", 0)
        return [_fill(schema.get("items", {}), defs, depth + 1) for _ in range(minimum)]
    if kind == "string":
        return "risposta di prova"
    if kind == "integer":
        return int(schema.get("minimum", 0))
    if kind == "number":
        return float(schema.get("minimum", 0))
    if kind == "boolean":
        return False
    return None


def _structured(body: dict) -> tuple[str | None, dict | None]:
    """`(json_text, tool_call)` se la richiesta vuole una risposta strutturata."""
    fmt = body.get("response_format") or {}
    if fmt.get("type") == "json_object":
        # Mem0: l'estrattore dei fatti e l'aggiornamento della memoria.
        return json.dumps({"facts": [], "memory": []}), None
    if fmt.get("type") == "json_schema":
        schema = fmt["json_schema"].get("schema", {})
        return json.dumps(_fill(schema, schema.get("$defs", {}))), None
    choice = body.get("tool_choice")
    tools = body.get("tools") or []
    if tools and choice not in (None, "auto", "none"):
        name = choice.get("function", {}).get("name") if isinstance(choice, dict) else None
        tool = next((t for t in tools if t["function"]["name"] == name), tools[0])
        params = tool["function"].get("parameters", {})
        args = json.dumps(_fill(params, params.get("$defs", {})))
        return None, {"id": f"call_{uuid.uuid4().hex[:12]}", "type": "function",
                      "function": {"name": tool["function"]["name"], "arguments": args}}
    return None, None


def _usage(prompt_chars: int, completion: int) -> dict:
    prompt = max(1, prompt_chars // 4)
    return {"prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": prompt + completion,
            "prompt_tokens_details": {"cached_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 0}}


@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    if os.environ.get("FAKE_LOG"):
        fmt = (body.get("response_format") or {}).get("json_schema", {}).get("name")
        tools = [t["function"]["name"] for t in body.get("tools") or []]
        print(json.dumps({"stream": bool(body.get("stream")), "format": fmt, "tools": tools[:5],
                          "tool_choice": body.get("tool_choice"),
                          "system": str((body.get("messages") or [{}])[0].get("content"))[:80]}),
              flush=True)
    model = body.get("model", "fake")
    prompt_chars = len(json.dumps(body.get("messages", [])))
    text, tool_call = _structured(body)
    created = int(time.time())
    cid = f"chatcmpl-{uuid.uuid4().hex[:16]}"

    if text is not None or tool_call is not None or not body.get("stream"):
        _stats["structured" if (text or tool_call) else "chat"] += 1
        await asyncio.sleep(STRUCTURED_S * random.uniform(0.7, 1.3))
        if text is None and tool_call is None:
            text = " ".join(_WORDS[: min(len(_WORDS), ANSWER_TOKENS)])
        message: dict[str, Any] = {"role": "assistant", "content": text}
        if tool_call:
            message = {"role": "assistant", "content": None, "tool_calls": [tool_call]}
        result = {
            "id": cid, "object": "chat.completion", "created": created, "model": model,
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if tool_call else "stop"}],
            "usage": _usage(prompt_chars, 60),
        }
        if not body.get("stream"):
            return JSONResponse(result)

        async def single():
            delta = {"role": "assistant", **({"content": text} if text else {"tool_calls": [
                {"index": 0, **tool_call}]})}
            chunk = {"id": cid, "object": "chat.completion.chunk", "created": created,
                     "model": model, "choices": [{"index": 0, "delta": delta,
                                                  "finish_reason": result["choices"][0]["finish_reason"]}]}
            yield f"data: {json.dumps(chunk)}\n\n"
            yield f"data: {json.dumps({**chunk, 'choices': [], 'usage': result['usage']})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(single(), media_type="text/event-stream")

    _stats["chat_stream"] += 1

    async def stream():
        await asyncio.sleep(TTFT_S * random.uniform(0.7, 1.3))
        words = [_WORDS[i % len(_WORDS)] for i in range(ANSWER_TOKENS)]
        for i, word in enumerate(words):
            delta = {"content": ("" if i == 0 else " ") + word}
            if i == 0:
                delta["role"] = "assistant"
            chunk = {"id": cid, "object": "chat.completion.chunk", "created": created,
                     "model": model, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
            yield f"data: {json.dumps(chunk)}\n\n"
            await asyncio.sleep(1 / TOKENS_PER_S)
        end = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
               "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
        yield f"data: {json.dumps(end)}\n\n"
        usage = {**end, "choices": [], "usage": _usage(prompt_chars, ANSWER_TOKENS)}
        yield f"data: {json.dumps(usage)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/v1/embeddings")
async def embeddings(request: Request):
    body = await request.json()
    inputs = body.get("input") or []
    if isinstance(inputs, str):
        inputs = [inputs]
    dims = int(body.get("dimensions") or 1536)
    _stats["embeddings"] += 1
    await asyncio.sleep(0.15)
    data = []
    for i, text in enumerate(inputs):
        rnd = random.Random(hash(str(text)))
        data.append({"object": "embedding", "index": i,
                     "embedding": [rnd.uniform(-1, 1) for _ in range(dims)]})
    return {"object": "list", "data": data, "model": body.get("model", "fake"),
            "usage": {"prompt_tokens": 10 * len(inputs), "total_tokens": 10 * len(inputs)}}


@app.get("/auth/v1/.well-known/jwks.json")
async def jwks():
    return json.loads(JWKS_FILE.read_text(encoding="utf-8"))


@app.get("/stats")
async def stats():
    return _stats


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8099)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()

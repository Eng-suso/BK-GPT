#!/usr/bin/env node
/**
 * Lo streaming della chat di DeliR per i media di lancio.
 *
 * `page.route` di Playwright risponde in un colpo solo: una risposta dell'agente
 * apparirebbe intera, e a schermo sembrerebbe finta. Questo server parla il
 * protocollo del backend (`POST .../messages/stream`, NDJSON): prima le fasi di
 * lavoro con le etichette di `backend/services/agent_progress.py`, poi il testo
 * a pezzi, con le pause di una generazione vera, poi `done`.
 *
 * Il copione del turno arriva nel corpo della richiesta (`__script`), messo dal
 * mock (`mockApi.ts`): il server non conosce il caso, lo recita.
 */
import { createServer } from "node:http";

const PORT = Number(process.env.LAUNCH_STREAM_PORT ?? 8000);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "*",
};

/**
 * Pezzi di 1-3 parole, come i token che arrivano dal modello. Un grassetto
 * arriva intero: a meta' il Markdown mostrerebbe gli asterischi.
 */
function tokens(text) {
  const words = text.split(/(\*\*[^*]+\*\*\S*\s*)|(?<=\s)/).filter(Boolean);
  const out = [];
  for (let i = 0; i < words.length; ) {
    const size = 1 + ((i * 7) % 3);
    out.push(words.slice(i, i + size).join(""));
    i += size;
  }
  return out;
}

createServer(async (req, res) => {
  if (req.method === "OPTIONS") {
    res.writeHead(204, CORS).end();
    return;
  }
  if (req.url === "/health") {
    res.writeHead(200, { ...CORS, "Content-Type": "application/json" }).end('{"status":"ok"}');
    return;
  }
  if (req.method !== "POST" || !/\/messages\/stream$/.test(req.url ?? "")) {
    res.writeHead(404, CORS).end();
    return;
  }
  let raw = "";
  for await (const chunk of req) raw += chunk;
  const script = JSON.parse(raw).__script ?? { phases: [], answer: "" };

  res.writeHead(200, { ...CORS, "Content-Type": "application/x-ndjson", "Cache-Control": "no-cache" });
  const send = (event) => res.write(`${JSON.stringify(event)}\n`);
  const started = Date.now();
  let sequence = 0;
  for (const phase of script.phases) {
    sequence += 1;
    send({
      type: "activity",
      message: phase.label,
      payload: {
        activity_id: `phase-${sequence}-${phase.id}`,
        phase: phase.id,
        label: phase.label,
        detail: phase.detail ?? "",
        icon: phase.icon,
        elapsed_ms: Date.now() - started,
        source: "phase",
      },
    });
    await sleep(phase.ms ?? 900);
  }
  for (const piece of tokens(script.answer)) {
    send({ type: "delta", content: piece });
    await sleep(/[.:;]\s*$/.test(piece) ? 160 : /\n/.test(piece) ? 120 : 38);
  }
  send({ type: "done", message: script.answer });
  res.end();
}).listen(PORT, "127.0.0.1", () => console.log(`stream DeliR su http://127.0.0.1:${PORT}`));

# Test di carico: 10 persone nello stesso momento

Domanda: DeliR regge **10 persone diverse, ognuna col suo account, che lavorano
nello stesso momento**? Risposta del 27 novembre 2026: **sì, con margine**.
Con 10 e con 20 persone non c'è stato nessun errore, e i tempi sono quelli di
una persona sola. I limiti veri stanno altrove (vedi *Cosa non misura*).

## Risultati

Ogni persona, per 5 minuti, ripete lo stesso giro:

1. un turno di chat;
2. l'elenco dei progetti, dei clienti e delle chat, più il contatore d'uso;
3. una volta ogni tre giri, una simulazione Prosimos da 200 casi, seguita fino alla fine.

Fra un'azione e l'altra c'è una pausa da persona di 2–5 secondi. Tutte partono
insieme.

| | 1 persona (base) | 10 persone | 20 persone |
|---|---:|---:|---:|
| Operazioni riuscite | 89 | 1.481 | 2.941 |
| Errori | 0 | 0 | 0 |
| Turno di chat, mediana (p50) | 6,6 s | 6,6 s | 6,7 s |
| Turno di chat, 95 su 100 entro (p95) | 10,4 s | 10,8 s | 10,8 s |
| Simulazione da 200 casi, p95 | 2,0 s | 2,1 s | 2,1 s |
| Elenco progetti, p95 | 0,01 s | 0,03 s | 0,03 s |
| Memoria del processo dell'app, picco | 574 MB | 575 MB | 586 MB |
| Connessioni Postgres, picco | 19 | 19 | 17 |

Il turno di chat dura quanto dura il modello: il finto modello impiega da solo
circa 6 s per turno (classificazione, router, risposta). Con 20 persone il p95
cresce di 0,4 s rispetto a una persona sola, quindi l'attesa dovuta al carico
è trascurabile. La memoria resta sotto il tetto di 1,5 GB che il compose di
produzione dà all'app.

Dettaglio per operazione, con gli esempi di errore se ce ne fossero:
[1 persona](2026-11-27-1-persona/results.md),
[10 persone](2026-11-27-10-persone/results.md),
[20 persone](2026-11-27-20-persone/results.md).

## Come è fatto

- **App come in produzione.** Un solo processo uvicorn, worker delle code
  nello stesso processo, login per persona con Supabase (token ES256 verificati
  sul JWKS), `DELIR_ALLOWED_EMAILS`, limiti di spesa accesi con listino, Postgres
  16 con pgvector, Neo4j 5, Mem0 e il runner Prosimos 2.1 veri.
- **Dieci account veri.** Ogni persona virtuale ha il suo `sub` e il suo token,
  quindi lavora nel suo spazio `acct-<sub>`, con la sua memoria e il suo
  registro dei consumi.
- **Modello finto con tempi veri** (`scripts/load_test/fake_openai.py`). Primo
  token dopo 0,8 s, poi 40 token al secondo; 1,2 s per le risposte strutturate;
  0,15 s per gli embedding. Si misura DeliR, non OpenAI, e non si spende niente.
  Le risposte strutturate si riempiono dallo schema JSON richiesto, con i
  default dello schema, cioè il percorso normale del router.
- **Macchina:** 4 CPU e 15 GB, più della VM di produzione prevista (2 OCPU e
  12 GB). L'app ha usato meno di 600 MB.

## Cosa non misura

1. **Il fornitore vero.** Con 10 persone il limite reale saranno i limiti di
   velocità dell'account OpenAI: un turno vero fa 3–6 chiamate al modello più
   gli embedding. Va verificato il livello dell'account (decisione di Sohayb).
2. **La lettura dei documenti.** docling non c'era in questo ambiente, quindi i
   caricamenti di PDF non sono nel giro. docling converte un documento alla
   volta: più caricamenti insieme si mettono in coda.
3. **La VM vera.** Qui c'erano 4 CPU invece di 2. Va rifatto il test sulla VM
   prima di aprire alle persone.

## Difetto trovato: la risposta non arriva parola per parola

Il primo pezzo di risposta arriva insieme all'ultimo: `chat_first_token` è
uguale a `chat_turn` in tutte le misure.

La causa: la risposta del consulente si genera dentro un sotto-grafo LangGraph
(`consulting_subgraph`), e `agent.stream(...)` in
`backend/services/agent_runtime.py` non chiede gli eventi dei sotto-grafi. Il
browser riceve così un solo `delta`, a risposta finita, dopo tutto il turno.

Con il modello vero vuol dire 10–20 secondi di schermo fermo, mostrando solo la
fase in corso. Non dipende dal carico. La correzione va fatta con cura: le
passate degli specialisti devono restare mute verso il consulente
(`findings_channel`).

## Rifarlo

```bash
scripts/vpt_stack.sh start                        # Postgres + Prosimos
# Neo4j 5 sulla porta 7687, password ci-neo4j (in CI lo alza docker compose)
uv run python -c "from pathlib import Path; from scripts.load_test.run import make_keys; make_keys(Path('/var/tmp/delir-load'))"
FAKE_JWKS_FILE=/var/tmp/delir-load/jwks.json uv run python -m scripts.load_test.fake_openai --port 8099 &
set -a; source scripts/load_test/app.env.example; set +a
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000 --workers 1 &
uv run python -m scripts.load_test.run --users 10 --minutes 5 \
  --pg-dsn postgresql://delir_super:ci-super@127.0.0.1:5432/postgres \
  --out docs/load-test/<data>-10-persone
```

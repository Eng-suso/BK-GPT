# Contatore d'uso della prova: come si usa

Il contatore misura quanto usa ogni consulente e ferma la **richiesta successiva**
quando una finestra è esaurita. Un lavoro già iniziato, come un turno di chat o
un file in lettura, arriva sempre in fondo. Il codice è in `backend/llm/budget.py`;
il pannello è in `frontend/src/features/usage/`.

## Accenderlo

Nel `.env` del backend:

```bash
LLM_PRICES_JSON={"gpt-5.6-luna": {"input": 0.20, "output": 1.20, "cached_input": 0.02}}
USAGE_LIMITS_ENABLED=true
USAGE_SESSION_HOURS=5
USAGE_SESSION_BUDGET_USD=1.5
USAGE_WEEK_BUDGET_USD=6
USAGE_TRIAL_BUDGET_USD=20     # 0 = nessun tetto sulla prova
USAGE_TRIAL_DAYS=14
USAGE_UNPRICED_USD_PER_MILLION_TOKENS=10
USAGE_WEEK_AUDIO_HOURS=6      # ore di registrazione a settimana; 0 = nessun tetto
USAGE_TRIAL_AUDIO_HOURS=10    # ore di registrazione nella prova
```

Il listino dell'audio va a minuto:

```bash
LLM_PRICES_JSON={..., "gpt-realtime-whisper": {"per_minute": 0.017}, "gpt-4o-transcribe-diarize": {"per_minute": 0.006}}
```

Note:

- **Per i modelli Claude il listino vuole anche `cache_write`**, il prezzo della
  scrittura in cache (1,25 volte l'ingresso): Anthropic la fa pagare, OpenAI no.
- **I prezzi del listino vanno messi per tutti i modelli usati.** Una riga senza
  prezzo si conta a `USAGE_UNPRICED_USD_PER_MILLION_TOKENS`, che è alto di
  proposito: un costo sconosciuto fa scattare il limite prima, mai dopo.
  `uv run python scripts/llm_spend.py listino` dice quali
  modelli mancano.
- **Spento, l'anello non compare** e nessuna richiesta viene fermata. Il registro
  dei consumi continua a contare.
- **Il limite per persona va acceso solo con l'identità Supabase.** Con il token
  condiviso, chi è il consulente lo dice un header scelto dal client.

## Il freno d'emergenza: un tetto per tutta l'installazione

```bash
USAGE_HARD_CAP_DAILY_USD=15   # 0 = spento
```

Il contatore per consulente ferma la richiesta successiva, ma lascia finire il
lavoro già accettato: lettura dei file, grafo, memoria, ricostruzione del piano.
Un difetto che fa partire cento chiamate in background non lo ferma nessun
limite per persona. Questo tetto sì: guarda quanto ha speso **tutta
l'installazione nelle ultime 24 ore** (dal registro dei consumi, le righe senza
prezzo al prezzo di ripiego) e, quando lo supera:

- **le code si fermano**: i worker non prendono lavori nuovi, che restano in
  coda e ripartono da soli quando la finestra delle 24 ore scorre (anche i
  worker in processi a sé, `python -m backend.workers.*`);
- **le chiamate nuove si rifiutano**: gateway, client della chat, Mem0. La riga
  del registro dice `refused` / `SpendCapReached`, e ogni funzione che sa andare
  avanti senza chiave (rerank lessicale, entità per regole) fa lo stesso;
- **chat, azioni dirette e registrazioni rispondono 429** con un messaggio per il
  consulente.

Vale anche con `USAGE_LIMITS_ENABLED=false`. Non sostituisce il limite di spesa
sulla console di OpenAI e di Anthropic, che resta la rete di sicurezza per ciò
che il registro non vede: lo rende raro. Come scegliere il valore: due o tre
volte la spesa di una giornata intensa di tutti i consulenti attivi.

## L'audio, in ore

Registrazioni dal vivo e file audio trascritti hanno un tetto **in ore**,
separato dai dollari dei modelli: per la settimana e per la prova. Il consulente
lo vede nel pannello come "2 h 10 min su 6 h". A ore finite si fermano solo le
nuove registrazioni e trascrizioni; la chat e il resto continuano.

- **Dal vivo:** si contano i secondi di audio mandati a OpenAI, cioè quello che
  si paga. La riga `live_transcription` si apre all'inizio e si aggiorna ogni 30
  secondi: un riavvio non perde minuti, e il pannello li vede mentre si
  registra. Il tetto si controlla all'apertura. Una registrazione si chiude al
  tetto più 10 minuti di margine, e ce n'è una sola alla volta per consulente.
- **La seconda passata non conta due volte.** All'arresto il browser manda lo
  stesso audio per la trascrizione con i nomi di chi parla. Se c'è una
  registrazione dal vivo dello stesso consulente finita da meno di 15 minuti,
  il file è la sua seconda passata: il costo resta nel registro
  (`transcription_after_live`), non consuma ore e non viene mai rifiutato.
- **File caricati a sé:** la durata viene dalla risposta della trascrizione
  (`duration`, o `usage.seconds`), e il tetto si controlla nella rotta. Una
  trascrizione di cui il fornitore non dice la durata resta nel budget in
  dollari dei modelli, invece di sparire da entrambi.

## Le tre finestre

| Finestra | Inizio | Durata |
|---|---|---|
| Sessione | alla prima richiesta, quando non ce n'è una aperta | `USAGE_SESSION_HOURS` |
| Settimana | a blocchi di 7 giorni dall'inizio della prova | 7 giorni |
| Prova | alla prima richiesta del consulente | `USAGE_TRIAL_DAYS` (o la data scelta dall'amministratore) |

Cosa si ferma quando una finestra è esaurita, sempre **all'ingresso** e mai a metà
di un lavoro:

- un **nuovo turno di chat**, all'inizio del turno;
- le **azioni dirette**, con la dipendenza di rotta `require_usage_available`:
  Genera BPMN e la sua riparazione dopo il confronto, what-if, racconto della
  simulazione, trascrizione, chat non in streaming.

Cosa non si ferma:

- il lavoro in background già accettato: lettura dei file, grafo, memoria,
  ricostruzione del piano;
- tutto quello che gira dentro un'azione già accettata;
- l'abbinamento delle affermazioni alle attività, che costa poco e ha già un
  ripiego lessicale.

Il gateway non controlla il limite: se lo facesse a ogni chiamata, potrebbe
fermare a metà un lavoro già accettato.

## Come scegliere le soglie

1. Misura una giornata tipica di un consulente con i prezzi configurati:
   `uv run python scripts/llm_spend.py --giorni 1`.
2. Budget della settimana = budget totale della prova / consulenti / settimane,
   meno un margine (per esempio 20%) per il lavoro in background.
3. Sessione ≈ un quarto o un terzo della settimana: così servono almeno 3-4
   sessioni per finire la settimana.

## Gestire un consulente (amministratore)

Con `X-DeliR-Admin-Token`:

```bash
# Vedere stato e importi
curl -H "Authorization: Bearer $TOKEN" -H "X-DeliR-Admin-Token: $ADMIN" \
  https://<host>/v1/usage/plans/<user_id>

# Ripristinare la sessione, alzare la settimana, allungare la prova
curl -X PUT -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" -H "X-DeliR-Admin-Token: $ADMIN" \
  -d '{"reset_session": true, "week_budget_usd": "10", "trial_ends_at": "2026-12-31T23:59:00Z"}' \
  https://<host>/v1/usage/plans/<user_id>
```

Il consulente vede solo percentuali e orari (`GET /v1/usage/me`); gli importi li
vede l'amministratore.

## Schermate

Le schermate desktop e mobile sono in `docs/usage-limits/ux/`. Le rigenera
`e2e/usage-meter.spec.ts`, in tre stati: ritmo da tenere d'occhio, quasi al
limite, sessione esaurita.

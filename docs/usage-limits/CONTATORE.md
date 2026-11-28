# Contatore d'uso della prova: come si usa

Il contatore misura quanto usa ogni consulente e ferma la **richiesta successiva**
quando una finestra è esaurita. Un lavoro già iniziato, come un turno di chat o
un file in lettura, arriva sempre in fondo. Il codice è in `backend/llm/budget.py`;
il pannello è in `frontend/src/features/usage/`.

## Accenderlo

Nel `.env` del backend:

```bash
LLM_PRICES_JSON={"gpt-6-luna": {"input": 0.10, "output": 0.50, "cached_input": 0.01}, "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cached_input": 0.01, "cache_write": 0.125}, "text-embedding-3-small": {"input": 0.02, "output": 0}, "gpt-realtime-whisper": {"per_minute": 0.017}, "gpt-4o-transcribe-diarize": {"per_minute": 0.006}}
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

- **I prezzi del listino vanno messi per tutti i modelli usati.** Una riga senza
  prezzo si conta a `USAGE_UNPRICED_USD_PER_MILLION_TOKENS`, che è alto di
  proposito: un costo sconosciuto fa scattare il limite prima, mai dopo.
  `uv run python scripts/llm_spend.py listino` dice quali
  modelli mancano.
- **Spento, l'anello non compare** e nessuna richiesta viene fermata. Il registro
  dei consumi continua a contare.
- **Il limite per persona va acceso solo con l'identità Supabase.** Con il token
  condiviso, chi è il consulente lo dice un header scelto dal client.

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

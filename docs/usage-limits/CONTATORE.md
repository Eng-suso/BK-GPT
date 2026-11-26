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

## Le tre finestre

| Finestra | Inizio | Durata |
|---|---|---|
| Sessione | alla prima richiesta, quando non ce n'è una aperta | `USAGE_SESSION_HOURS` |
| Settimana | a blocchi di 7 giorni dall'inizio della prova | 7 giorni |
| Prova | alla prima richiesta del consulente | `USAGE_TRIAL_DAYS` (o la data scelta dall'amministratore) |

Cosa si ferma quando una finestra è esaurita:

- un **nuovo turno di chat**;
- le **azioni dirette**: disegno BPMN, abbinamento delle affermazioni,
  simulazione assistita, racconto della simulazione, trascrizione.

Cosa non si ferma: il lavoro in background già accettato (lettura dei file,
grafo, memoria, ricostruzione del piano) e tutto quello che gira dentro un turno
già iniziato.

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

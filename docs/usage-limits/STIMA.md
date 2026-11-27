# Quanto costa un consulente al giorno: stima dal codice, su tutto il software

Data: 2026-11-26. Script: `uv run python scripts/usage_day_estimate.py`.

**È una stima, non una misura.** Nessuna chiamata è partita. I pezzi fissi sono
letti dal codice vero: prompt di sistema, schemi di output, definizioni dei tool di
ogni specialista, memoria procedurale. I pezzi variabili sono ipotesi scritte in
`SCENARIOS` nello script e si cambiano lì: quante interviste, quanti turni, quanto
contesto. I token sono contati come caratteri / 4, quindi il risultato vale ±20%.

Lo script copre **ogni compito che spende**: tutti i valori di `LlmTask` (si ferma
se ne manca uno) più la trascrizione dal vivo. Resta escluso solo il giudice degli
eval, che non gira in produzione. La misura vera resta
`uv run python scripts/llm_spend.py --giorni 1` con il listino configurato.

## Listini ufficiali (USD)

| Voce | Ingresso | Dalla cache | Uscita | Note |
|---|---|---|---|---|
| GPT-6 Luna | $0.10 / M | $0.01 / M | $0.50 / M | oltre 272K token di prompt: ×2 su ingresso e cache, ×1.5 su uscita |
| Claude Haiku 5.5 | $0.10 / M | $0.01 / M | $0.50 / M | oltre 100K token di prompt: ×5 |
| text-embedding-3-small | $0.02 / M | | | |
| gpt-realtime-whisper (trascrizione dal vivo) | $0.017 / minuto | | | |
| gpt-4o-transcribe-diarize (file audio) | ≈ $0.006 / minuto | | | modello deprecato: è la stima di OpenAI per gpt-4o-transcribe, che ha le stesse tariffe a token |

Fonti:
[GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna),
[Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing),
[text-embedding-3-small](https://developers.openai.com/api/docs/models/text-embedding-3-small),
[gpt-realtime-whisper](https://developers.openai.com/api/docs/models/gpt-realtime-whisper),
[gpt-4o-transcribe-diarize](https://platform.openai.com/docs/models/gpt-4o-transcribe-diarize),
[OpenAI pricing](https://developers.openai.com/api/docs/pricing?latest-pricing=standard).

**Luna e Haiku costano uguale nell'uso normale.** La scelta fra i due conta per la
qualità, non per il costo. L'unica differenza di prezzo è la soglia dei prompt
lunghi: 100K token per Haiku, 272K per Luna.

## Le due giornate

| | Tipica | Intensa |
|---|---|---|
| Fonti | 2 interviste (testo) | 4 interviste + 6 documenti |
| Audio | nessuno | 1 ora di file + 2 ore registrate dal vivo |
| Processi | 1 (2 piani, 2 BPMN) | 3 (6 piani, 3 unificazioni, 6 BPMN, 2 riparazioni dopo il confronto) |
| Chat | 40 turni, 2,5 passi, 3 specialisti | 150 turni, 3 passi, tutti e 10 gli specialisti |
| Contesto di scope | 12.000 token | 24.000 token |
| Memoria | 10 fatti, senza estrazione | 30 fatti con estrazione Mem0, 3 playbook |
| Simulazione | 3 what-if, 2 racconti | 15 what-if, 6 racconti |

## Risultato

| | Tipica | Intensa |
|---|---|---|
| **Totale** | **$0.30** | **$4.34** |
| di cui trascrizione dal vivo | — | $2.04 (47%) |
| di cui file audio | — | $0.36 (8%) |
| di cui modelli di linguaggio | $0.29 | $1.93 |
| di cui embedding | $0.0004 | $0.002 |

Il totale è identico per Luna e per Haiku. Senza cache la giornata intensa sale a
$4.46.

### Dove va la spesa dei modelli nella giornata intensa

| Voce | Costo |
|---|---|
| Chat, modellazione / evidenze / scoperta | $0.93 |
| Chat, canvas (macro, patch, costruzione) | $0.29 |
| Chat, revisione e consulenza (home, clienti, setup) | $0.36 |
| Confronto con le fonti | $0.08 |
| Estrazione del piano (comprese le riparazioni) | $0.08 |
| Affermazioni e confronto fra fonti | $0.06 |
| Rerank, instradamento, riassunto | $0.08 |
| Qualità del piano, unificazione, memoria, playbook, entità, simulazione | $0.05 |

**Due lezioni.**
- **Quando c'è audio, l'audio pesa più di tutto il resto.** Due ore registrate dal
  vivo costano più di 150 turni di chat.
- **Senza audio, la chat è l'80% della spesa.** A ogni passo rimanda le definizioni
  dei tool (fino a 14.000 token) e il contesto.

Il prompt più lungo della giornata intensa è di 43.670 token: sotto la soglia dei
prompt lunghi di entrambi i modelli.

## Un buco trovato con la stima (chiuso)

**Chiuso il 2026-11-27:** la registrazione dal vivo ora lascia una riga nel
registro con i secondi di audio e guarda il tetto delle ore all'apertura; l'audio
ha il suo limite in ore (vedi `CONTATORE.md`).

Com'era: **la trascrizione dal vivo non era misurata né limitata.** Il WebSocket
`/live-transcription` va direttamente a OpenAI: non apre un'operazione, non scrive
nel registro dei consumi e non passa dal contatore d'uso. Eppure è la voce più cara
dell'uso intenso.

Va chiusa prima di accendere i limiti:
- una riga nel registro per sessione di registrazione, con i minuti e il costo al
  minuto;
- il controllo del limite all'apertura del WebSocket.

## Budget per la prova

I minuti di audio sono prevedibili e costano più di tutto il resto, quindi
conviene tenerli fuori dal budget dei modelli. Le soglie dei modelli restano
strette, e l'audio ha il suo tetto in minuti:

| Finestra | Modelli di linguaggio | Audio |
|---|---|---|
| Sessione (5 ore) | **$1.20** (5 ore di una giornata intensa) | — |
| Settimana | **$5.00** (2 giornate intense + 3 tipiche) | **6 ore** |
| Prova (14 giorni) | **$10.00** | **10 ore** (≈ $10 dal vivo) |

**Costo massimo di un consulente sull'intera prova: circa $20** ($10 di modelli più
$10 di audio). Con 20 consulenti sono circa $400 nel caso peggiore: tutti al tetto,
tutti i giorni. Con un uso tipico, testo e qualche ora di audio, restano fra $3 e
$6 a testa.

Se si preferisce un budget unico che comprenda l'audio: sessione $2.50, settimana
$10, prova $20.

`.env` per la parte modelli:

```bash
USAGE_LIMITS_ENABLED=true
USAGE_SESSION_BUDGET_USD=1.20
USAGE_WEEK_BUDGET_USD=5.00
USAGE_TRIAL_BUDGET_USD=10.00
USAGE_TRIAL_DAYS=14
USAGE_WEEK_AUDIO_HOURS=6
USAGE_TRIAL_AUDIO_HOURS=10
LLM_PRICES_JSON={"gpt-6-luna": {"input": 0.10, "output": 0.50, "cached_input": 0.01}, "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cached_input": 0.01}, "text-embedding-3-small": {"input": 0.02, "output": 0}, "gpt-realtime-whisper": {"per_minute": 0.017}, "gpt-4o-transcribe-diarize": {"per_minute": 0.006}}
```

**Il listino va configurato.** Senza, ogni riga si conta al prezzo di ripiego
($10 per milione di token, cento volte il prezzo vero) e il limite scatta dopo
pochi turni.

## Cosa serve per usare davvero Luna e Haiku

1. **Haiku non si può ancora chiamare.** Il gateway costruisce solo client
   OpenAI (`langchain_openai`): serve un client Anthropic in `backend/llm/`,
   scelto per compito dal profilo.
2. **Mem0 usa `gpt-4o-mini`** (`MEM0_LLM_MODEL`). Per restare su Luna e Haiku va
   impostato `MEM0_LLM_MODEL=gpt-6-luna`.
3. **Ripartizione suggerita**, da validare con gli eval:
   - Luna per la chat e per l'estrazione del piano, che con molte fonti può
     superare i 100K token, dove Haiku costerebbe 5 volte tanto;
   - Haiku per i compiti piccoli con schema stretto: instradamento, rerank,
     giudizio sulle entità, what-if, racconto, abbinamento delle affermazioni.

   Il costo non cambia: lo scopo è la qualità.
4. **La leva più grossa sui modelli resta la chat.** Mandare le definizioni dei
   tool pesanti (`prepare_process_understanding_review`, `amend_process_plan`)
   solo nel passo che le usa taglierebbe circa un terzo della spesa della chat.

## Rischi della stima

- **Il ragionamento è stimato.** Si assume quanto l'uscita per `medium`, il 30%
  per `low`, zero per `none`.
- **Il contesto di scope è un'ipotesi.** È a 12.000 o 24.000 token; un processo
  grande arriva al tetto di 48.000 e la chat costa fino al doppio.
- **La trascrizione dei file è una stima a minuto.** Il modello diarize è
  deprecato e non ha un prezzo al minuto pubblicato; va sostituito.
- **La ricerca web (Tavily) e la lettura dei documenti (docling) non sono
  incluse:** la prima ha un listino suo, la seconda è self-hosted.

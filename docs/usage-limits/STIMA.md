# Quanto costa un consulente al giorno: stima dal codice

Data: 2026-11-26. Script: `scripts/usage_day_estimate.py`.

**È una stima, non una misura.** Nessuna chiamata è partita. I pezzi fissi (prompt
di sistema, schemi di output, definizioni dei tool, memoria procedurale) sono
letti dal codice vero. I pezzi variabili (lunghezza di un'intervista, contesto,
turni al giorno) sono ipotesi scritte in `DAY` nello script, e si cambiano lì. I
token sono contati come caratteri / 4, quindi il risultato va letto come ±20%. La
misura vera resta `uv run python scripts/llm_spend.py --giorni 1` con il listino
configurato.

## Listini ufficiali (USD per milione di token)

| Modello | Ingresso | Dalla cache | Scrittura in cache | Uscita | Prompt lunghi |
|---|---|---|---|---|---|
| GPT-6 Luna | $0.10 | $0.01 | $0.125 | $0.50 | oltre 272K token: ×2 su ingresso e cache, ×1.5 su uscita |
| Claude Haiku 5.5 | $0.10 | $0.01 | $0.125 | $0.50 | oltre 100K token: $0.50 in ingresso / $2.50 in uscita (×5) |
| text-embedding-3-small | $0.02 | | | | |

Fonti: [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna),
[Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing),
[text-embedding-3-small](https://developers.openai.com/api/docs/models/text-embedding-3-small).

**I due modelli costano uguale nell'uso normale.** La scelta fra i due conta per la
qualità, non per il costo, tranne su un punto: la soglia di Haiku per i prompt
lunghi è a 100K token, quella di Luna a 272K.

## La giornata tipica (ipotesi)

- 2 interviste da circa 45 minuti (40.000 caratteri ciascuna);
- 2 ricostruzioni del piano;
- 2 «Genera BPMN», con il confronto con le fonti;
- 40 turni di chat, con 2,5 passi per turno;
- 3 what-if, 2 racconti della simulazione, 20 giudizi sulle entità, 10 fatti in memoria.

## Risultato

| | Costo al giorno |
|---|---|
| Giornata tipica | **$0.29** |
| La stessa, senza cache | $0.33 |
| Giornata pesante (100 turni, 4 interviste) | **$0.72** |

Il risultato è identico per Luna e per Haiku.

Dove va la spesa nella giornata tipica:

| Voce | Costo | Token in ingresso per chiamata |
|---|---|---|
| Chat, specialista di modellazione | $0.081 | 30.170 |
| Chat, specialista delle evidenze | $0.076 | 28.034 |
| Chat, specialista di scoperta | $0.074 | 17.722 |
| Estrazione del piano | $0.018 | 28.675 |
| Confronto con le fonti | $0.013 | 11.975 |
| Affermazioni delle fonti | $0.008 | 10.380 |
| Tutto il resto (instradamento, rerank, riassunto, qualità, entità, simulazione) | $0.023 | |
| Embedding (grafo e memoria) | $0.0004 | |

**La chat è il 78% della spesa.** Ogni passo rimanda la memoria procedurale (1.600
token), le definizioni dei tool dello specialista (fino a 14.000) e il contesto di
scope (12.000 nell'ipotesi). Il knowledge graph, dopo la correzione del
ri-embedding, pesa meno di un millesimo di dollaro al giorno.

## Budget consigliati per la prova

| Finestra | Soglia | Perché |
|---|---|---|
| Sessione (5 ore) | **$0.40** | Una mattinata pesante: circa 50 turni con documenti |
| Settimana | **$2.00** | 5 giornate tipiche ($1.45) più un margine per una pesante |
| Prova (14 giorni) | **$4.00** | Due settimane piene |

Con questi numeri **un consulente in prova costa al massimo $4** in 14 giorni: 20
consulenti costano al massimo $80. I default attuali (`$1.5` / `$6` / `$20`) sono da
4 a 5 volte più larghi. Vanno abbassati quando si accendono i limiti, dopo una
misura vera.

`.env` corrispondente:

```bash
USAGE_LIMITS_ENABLED=true
USAGE_SESSION_BUDGET_USD=0.40
USAGE_WEEK_BUDGET_USD=2.00
USAGE_TRIAL_BUDGET_USD=4.00
USAGE_TRIAL_DAYS=14
LLM_PRICES_JSON={"gpt-6-luna": {"input": 0.10, "output": 0.50, "cached_input": 0.01}, "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cached_input": 0.01}, "text-embedding-3-small": {"input": 0.02, "output": 0}}
```

**Il listino va configurato.** Senza, ogni riga si conta al prezzo di ripiego
($10 per milione di token, cento volte il prezzo vero) e il limite scatta dopo
pochi turni.

## Cosa serve per usare davvero Luna e Haiku

1. **Haiku non si può ancora chiamare.** Il gateway costruisce solo client
   OpenAI (`langchain_openai`). Per Haiku serve un client Anthropic in
   `backend/llm/`, scelto per compito dal profilo (`TaskProfile.model_name`).
2. **Modello per compito.** Una ripartizione ragionevole, da validare con gli
   eval:
   - Luna per la chat e per l'estrazione del piano, che può superare i 100K
     token con molte interviste;
   - Haiku per i compiti piccoli con schema stretto: instradamento, rerank,
     giudizio sulle entità, what-if, racconto.

   Il costo non cambia: lo scopo è la qualità.
3. **La leva più grossa resta la chat.** Mandare le definizioni dei tool pesanti
   (`prepare_process_understanding_review`, `amend_process_plan`) solo nel passo
   che le usa taglierebbe circa un terzo della spesa della chat.

## Rischi della stima

- **Il ragionamento è stimato.** Si assume quanto l'uscita per `medium`, il 30%
  per `low`, zero per `none`. Un modello che ragiona di più costa di più
  sull'estrazione.
- **Il contesto di scope a 12.000 token è un'ipotesi media.** Un processo grande
  arriva al tetto di 48.000: allora la chat costa circa il doppio.
- **La trascrizione audio non è inclusa:** ha un listino a parte.
- **Prompt lunghi su Haiku:** con più di 8-9 interviste per processo, l'estrazione
  del piano supera i 100K token e su Haiku costa 5 volte tanto. È il motivo per
  tenerla su Luna.

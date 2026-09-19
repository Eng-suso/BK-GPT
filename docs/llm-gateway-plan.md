# Spesa LLM governata: prima evitare la chiamata, poi misurarla, poi sceglierla

Stato: **piano**, nessuna fase implementata. 2026-09-18.
Sintesi di due analisi: l'architettura del gateway (invarianti, budget con
prenotazione, strategie dichiarate) e il confronto con le pratiche documentate da
AWS, OpenAI, Anthropic, Cloudflare, Vercel e FinOps Foundation (priorita' al
lavoro evitato, dipendenze fra artefatti, costo per risultato valido).

## 1. Il principio

> Si spendono token solo quando producono informazione nuova, risolvono
> un'incertezza, o danno un risultato che il codice e gli artefatti esistenti non
> possono dare in modo affidabile.

L'obiettivo non e' il costo per token piu' basso: e' un AS-IS corretto, un TO-BE
utile e un'analisi KPI affidabile al minor costo complessivo. Da qui l'ordine
delle leve, che e' anche l'ordine della roadmap:

1. **evitare la chiamata** (artefatti gia' prodotti, codice deterministico);
2. **misurarla** (senza misura ogni scelta successiva e' a occhio);
3. **ridurla** (meno token, un solo livello di retry);
4. **sceglierla** (il modello giusto per il compito, deciso dagli eval);
5. **scontarla** (cache del fornitore, Batch, Flex).

## 2. Lo stato di oggi

Ricostruito il 18/09, quando il credito OpenAI si e' esaurito senza che nessuno
sapesse dove fosse andato (LangSmith ha esaurito la quota mensile il 6/9; la
chiave del progetto non ha il permesso `api.usage.read`).

| Sintomo | Causa |
| --- | --- |
| Spesa non attribuibile | le chiamate partono da una decina di moduli, ognuno con il proprio client (`process_understanding`, `conformance_audit`, `plan_consolidation`, `reranker`, `entity_resolution`, `procedural/extraction`, `routing_contracts`, `agent.py`, `memory/embeddings.py`, Mem0); nessun punto di passaggio unico |
| I test pagano il modello vero | la chiave di `.env` vale per tutti: ~220 giudizi di qualita' reali in due giorni da tenant di test |
| Timeout pagati piu' volte | tre livelli di retry indipendenti (client, fonte, coda): nel caso peggiore ~100 richieste per una sintesi che fallisce (stima, da confermare con la misura) |
| Il budget dell'agente non vede il costo | conta passi e chiamate a strumenti; «Genera BPMN» vale uno strumento e puo' contenere N estrazioni |
| Lavoro ripetuto | un'estrazione non ha identita': ogni ricostruzione del piano rilegge tutte le interviste |
| Estrazione poco affidabile | timeout a 60 s anche su interviste di 4.000 caratteri; piani diversi a ogni esecuzione; riferimenti rotti nei piani parziali |

Guardrail che esistono gia' e restano: budget del turno (`agent_budget.py`: 8
decisioni, 12 strumenti, scadenza), cicli di correzione limitati (piano 2,
canvas 2, riparazioni di conformita'), code con massimo 5 tentativi e backoff.
Garantiscono che le cose finiscano; non governano il costo.

## 3. Dove il modello non serve

Ogni chiamata deve avere una ragione per cui codice e artefatti esistenti non
bastano. E' la regola del progetto (il runtime possiede cio' che puo'
verificare, il giudizio va al modello) applicata alla spesa, e diventa un
criterio di revisione del codice.

| Operazione | Come |
| --- | --- |
| Una fonte e' cambiata? | hash del contenuto e metadati |
| Uno schema JSON e' valido? | pydantic |
| Il BPMN e' sintatticamente e strutturalmente valido? | XSD, soundness, regole di dominio |
| KPI e simulazioni | motore di calcolo |
| Estrarre il processo da un'intervista nuova | modello, risultato persistito come artefatto |
| Risolvere una contraddizione fra voci | modello, solo quando il codice non la chiude |
| Proporre un TO-BE | modello scelto dagli eval |
| Rispondere con dati gia' strutturati | recupero e risposta diretta |

Validare il BPMN con il codice non certifica che sia fedele al lavoro reale: la
verifica sulle fonti (revisore di conformita') e la validazione del consulente
restano necessarie.

Da applicare subito come esame dei flussi esistenti: il giudizio di qualita' del
piano va rifatto a ogni scrittura, o solo quando il piano cambia? Quali flussi
del grafo della chat sono in realta' workflow prevedibili e non hanno bisogno di
un agente? («Genera BPMN» e' gia' un comando, non una conversazione: e' la
direzione giusta.)

## 4. Architettura

### 4.1 Il gateway minimo

Un solo punto di passaggio, perche' senza di esso non si misura niente. Chi
chiama dichiara **un compito**, non un modello:

```python
result = llm.run(
    task=LlmTask.PLAN_EXTRACTION,     # enum del compito
    prompt=PROMPTS.plan_extraction,   # prompt versionato (id + versione)
    input=payload,
    output=ProcessUnderstanding,      # schema pydantic, quando strutturato
)
```

Il minimo, che e' anche tutto cio' che si costruisce in P1:

- **registro dei compiti** (`TaskProfile`, configurazione versionata): modello,
  livello di ragionamento, massimo di token in uscita, timeout come funzione
  della dimensione dell'input, politica di retry, se e' differibile;
- **operazione corrente** (`contextvar`): tipo, tenant, progetto, processo, id.
  La aprono i punti d'ingresso - turno di chat, «Genera BPMN», job di
  `plan_worker`, `conformance_worker`, `ingest_worker`, eval - e la ereditano
  tutte le chiamate fatte dentro, anche dentro uno strumento o in un thread del
  pool di estrazione;
- **registro dei consumi** in Postgres: operazione, compito, versione del prompt,
  modello, token (ingresso, uscita, ragionamento, cache), durata, esito (`ok`,
  `timeout`, `error`, `cache_hit`), costo stimato da una tabella prezzi;
- **un solo livello di retry**, deciso dal gateway: si ritenta su rate limit e
  connessione, non su timeout di un compito lungo.

Rimandati finche' i dati non ne dimostrano l'utilita': piu' fornitori
(salvo la decisione su Azure UE, sezione 8), tracce OpenTelemetry con uno
strumento dedicato, semantic cache, router che chiama un modello per scegliere un
modello.

### 4.2 Artefatti con dipendenze, non solo cache

Salvare l'estrazione di un'intervista non basta: bisogna sapere cosa dipende da
cosa, per rifare solo cio' che una modifica invalida.

```
intervista (hash)  ->  piano parziale  ->  piano fuso  ->  consolidamento  ->  BPMN  ->  revisione di conformita'
                                              ^
                  risposte del consulente ----+   (precedenza piu' alta, mai rigenerate)
```

- **Controllo deterministico all'ingresso:** hash del contenuto confrontato con le
  versioni gia' elaborate. Fonte invariata: si recupera il piano parziale, zero
  chiamate. Fonte nuova o cambiata: si estrae solo quella.
- **Invalidazione a valle:** cambia una fonte, si rifanno il suo piano parziale e i
  passaggi successivi (fusione, consolidamento - una chiamata -, disegno,
  revisione solo sulle fonti toccate). Il resto si riusa. Oggi
  `evidence_source_set_id` dice su quale insieme di fonti e' nato il piano: va
  portato al livello della singola fonte.
- **Le risposte del consulente non sono artefatti da rigenerare.** Sono la fonte
  con la precedenza piu' alta: una ricostruzione del piano le riapplica, non le
  cancella.
- **Chiave dell'artefatto:** tenant + hash del testo + versione del prompt +
  versione dello schema di estrazione + modello + rilievi del revisore, quando
  ci sono. Il tenant e' nella chiave per costruzione: due clienti con lo stesso
  documento non condividono mai un risultato.

### 4.3 Budget: tre livelli sovrapposti

1. **Limite del fornitore.** Progetti e chiavi separati per sviluppo, eval e
   produzione, ognuno con il proprio tetto di spesa. E' la protezione contro una
   spesa complessiva fuori controllo, non un sostituto dei controlli
   applicativi. (Da verificare nel dashboard OpenAI se il tetto per progetto e'
   rigido o solo un avviso, e con quale ritardo si applica.)
2. **Budget di DeliR, gerarchico:** per operazione, per processo al giorno, per
   tenant al mese. Prima della chiamata si **prenota** il costo massimo ammesso,
   in modo atomico; dopo, si **salda** con il costo reale. Dopo un timeout il
   consumo e' incerto: la prenotazione non si libera, resta **da riconciliare**.
3. **Limiti dell'esecuzione:** per ogni operazione, tentativi, chiamate, token in
   uscita e tempo complessivo. Un retry consuma il budget dell'operazione
   originale e non duplica il job.

### 4.4 Scegliere dentro il tetto, senza fermarsi a meta' turno

Il budget del turno che interrompe l'agente resta come freno di emergenza. Il
modo normale di rispettare un tetto e' decidere **prima** come eseguire:

- l'operazione conosce i propri compiti prima di eseguirli (quante fonti,
  quanto lunghe, quali sono gia' in cache) e il runtime ne stima il costo;
- esistono varianti dichiarate come dati, e il runtime sceglie la prima che sta
  nel budget, **tenendo una riserva per la risposta**:

| Operazione | Completa | Se il budget non basta |
| --- | --- | --- |
| Sintesi del piano | fonti cambiate + fusione + consolidamento | piano attuale dichiarato indietro, ricostruzione in coda |
| Revisore di conformita' | agente sulle fonti toccate | verdetto `incomplete` dichiarato, agente in coda |
| Turno di chat | con strumenti | risposta dallo snapshot, con cio' che resta da fare |
| Ingestione nel grafo | risoluzione delle entita' con il modello solo sui casi incerti | confronto deterministico, casi incerti in coda |

- **Una verifica rigorosa non diventa superficiale in silenzio.** La validazione
  finale non ha una versione economica: si fa intera, oppure si rimanda e il
  risultato dice che manca.
- L'agente dichiara in forma tipizzata cio' che la richiesta esige (per esempio
  che serve un piano allineato all'ultima intervista); se la variante possibile
  non basta, la risposta lo dice e offre di attendere la coda.

### 4.5 Scelta del modello

Per tipo di compito, dalla configurazione del registro, senza una chiamata a un
modello per decidere quale modello chiamare. Ogni profilo si cambia solo sui
numeri: costo dal registro dei consumi, qualita' dal golden set.

| Compito | Partenza | Escalation |
| --- | --- | --- |
| Instradamento della richiesta | regole strutturali (scope, comando esplicito), mai parole chiave; modello piccolo se ambiguo | solo se ambiguo |
| Estrazione delle interviste | **deciso dagli eval**: e' il compito dove si concentrano i difetti di qualita', e un modello economico che fallisce costa due chiamate invece di una | se l'output non supera i controlli |
| Risoluzione delle entita' | confronto deterministico | modello per i casi incerti |
| Unificazione dei doppioni, revisore | modello scelto dagli eval | - |
| TO-BE | modello valutato su compiti complessi | ragionamento piu' profondo quando serve |
| KPI | calcolo deterministico | modello solo per spiegarli |

### 4.6 Sconti, per ultimi

- **Cache del prefisso del fornitore:** istruzioni e parti stabili in testa,
  dati variabili in coda. Riduce il costo dei token letti, non elimina la
  chiamata. (Soglie e prezzi da verificare sul listino del modello in uso.)
- **Batch API e Flex** solo per il lavoro davvero differibile: eval massivi,
  arricchimento del grafo, riesami periodici. Non per la chat, «Genera BPMN» o
  l'elaborazione di un'intervista che il consulente aspetta. Mettere un lavoro in
  coda non lo rende scontato.
- **Semantic cache:** no per evidenze, decisioni e validazioni. Due domande
  quasi uguali possono riferirsi a due versioni diverse del processo.

## 5. Invarianti

Verificate dal codice, non affidate alla disciplina.

| # | Invariante | Verifica |
| --- | --- | --- |
| L1 | Nessuna chiamata al modello fuori dal gateway | regola ast-grep in CI: `ChatOpenAI`, `openai`, `OpenAIEmbeddings` vietati fuori da `backend/llm/` |
| L2 | Ogni chiamata dichiara compito e operazione | il gateway rifiuta una chiamata senza operazione aperta |
| L3 | Nessuna chiamata senza prenotazione di budget | la prenotazione e' dentro `llm.run` |
| L4 | Ogni chiamata lascia un evento di consumo, anche se fallisce o e' servita dalla cache | test per esito |
| L5 | Ogni prompt ha id e versione | registro dei prompt; la versione entra nella chiave degli artefatti e nel registro dei consumi |
| L6 | I test non hanno una chiave; sviluppo, eval e produzione hanno chiavi e progetti distinti | fixture che rende impossibile costruire il client nei test non marcati `live_llm` |
| L7 | Un risultato ridotto o rimandato per budget lo dichiara in forma tipizzata | stesso schema del verdetto `incomplete` |
| L8 | Un artefatto e' sempre legato al suo tenant | il tenant e' nella chiave; test di isolamento |
| L9 | Le risposte del consulente sopravvivono a ogni ricostruzione | test: ricostruzione dopo una risposta, la risposta resta |
| L10 | Il registro interno coincide con la fattura del fornitore | riconciliazione giornaliera (serve una chiave admin con `api.usage.read`) |

## 6. Misura: costo per risultato valido

Il KPI non e' il costo per chiamata: e' **quanto costa un risultato che il
consulente puo' usare**. Il piano piu' caro e' quello che il consulente deve
rifare a mano, e oggi quel costo e' invisibile.

| Indicatore | Da dove |
| --- | --- |
| Costo per AS-IS validato | registro dei consumi per processo, fino alla validazione |
| Costo per TO-BE approvato | idem |
| Costo dei retry e delle chiamate fallite | esito nel registro |
| Chiamate evitate dagli artefatti | `cache_hit` nel registro |
| Per cliente, operazione, compito, modello | dimensioni del registro |

Il costo del prodotto include anche infrastruttura, embedding, retrieval e
osservabilita': una vista limitata alla fattura OpenAI non e' il costo totale.

## 7. Roadmap

Ogni fase ha un criterio d'uscita misurabile e lascia il sistema migliore anche
se ci si ferma li'.

**P0 - Fermare gli sprechi (1-2 giorni).**
- Test senza chiave (L6); gli eval marcati `live_llm`.
- Progetti e chiavi separati per sviluppo, eval e produzione, con tetto dal lato
  del fornitore.
- Un solo livello di retry; niente retry su timeout per le estrazioni lunghe.
- Tracing LangSmith spento finche' non c'e' un piano o un'alternativa.
- **Affidabilita' dell'estrazione**, perche' ottimizzare un'estrazione instabile
  vuol dire pagare meno per un risultato da rifare: timeout proporzionato alla
  lunghezza dell'intervista; riferimenti rotti nel piano parziale intercettati
  prima del merge e fatti correggere su quel punto, con la correzione verificata.

*Uscita:* la suite gira senza spesa reale; nessun job duplicato; un'intervista
lunga si estrae senza timeout.

**P1 - Misurare tutto (1 settimana).** Gateway minimo (4.1), migrazione di tutti
i punti di chiamata, regola L1 in CI, registro dei consumi.
*Uscita:* ogni chiamata e' contabilizzata e interrogabile per tenant, operazione,
compito; «dove sono andati i soldi ieri» e' una query.

**P2 - Eliminare il lavoro ripetuto (1 settimana).** Hash delle fonti, piani
parziali come artefatti (4.2), invalidazione a valle, risposte del consulente
riapplicate (L9), eval con record/replay delle estrazioni.
*Uscita:* rieseguire sulle stesse fonti non genera estrazioni; una quarta
intervista ne genera una; un eval ripetuto costa una chiamata.

**P3 - Budget e varianti (1-2 settimane).** Stima dei costi dai consumi misurati,
budget gerarchico con prenotazione e saldo (4.3), varianti dichiarate e riserva
per la risposta (4.4), un'operazione alla volta a partire dalla sintesi del
piano.
*Uscita:* con un tetto basso il consulente riceve sempre una risposta, dichiarata
completa o ridotta; il freno di emergenza non scatta.

**P4 - Scegliere il modello (continuo).** Profili per compito decisi dagli eval
(4.5); in CI un budget di token per operazione, come un budget di prestazione.
*Uscita:* ogni cambio di modello e' giustificato da costo e qualita' misurati.

**P5 - Ottimizzazione avanzata e governance (quando i dati lo giustificano, e
prima del primo cliente enterprise per la governance).** Cache del prefisso,
Batch/Flex per il differibile (4.6), tracce OpenTelemetry, riconciliazione con
il fornitore (L10), conservazione e cancellazione di prompt e risposte,
residenza dei dati.

## 8. Decisioni che servono da Sohayb

1. **Fornitore:** solo OpenAI, oppure Azure OpenAI in UE fin da subito? E' l'unica
   decisione che cambia P1.
2. **Tetti:** si fissano dopo due settimane di registro (P1), sui consumi veri.
3. **Risultati ridotti davanti al cliente:** dove sono accettabili (una bozza) e
   dove no (una validazione finale).
4. **LangSmith:** piano a pagamento o spento.
5. **Chiave admin del fornitore** per la riconciliazione, conservata solo lato
   server.

## 9. Da verificare prima di contarci

- Se il tetto di spesa per progetto su OpenAI e' rigido, e con quale ritardo si
  applica.
- Prezzi e soglie della cache del prefisso per il modello in uso (lo schema
  "sovrapprezzo sulla scrittura" e' di Anthropic; per OpenAI non risulta, ma va
  controllato sul listino corrente).
- Il moltiplicatore dei retry annidati (~100 richieste nel caso peggiore) e' una
  stima dal codice: lo conferma o lo smentisce il registro di P1.

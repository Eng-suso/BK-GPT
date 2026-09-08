# Provenance dell'evidenza — perché la chat di processo non può più attribuire male

Questo documento spiega cosa è cambiato dopo i test E2E V3, e soprattutto
*perché* la correzione sta nel codice e non nel prompt. Serve a chi tocca
`backend/memory/provenance.py`, i toolset dell'evidenza o il nodo che scrive la
risposta.

## Il difetto, in una riga

La chat sapeva **cosa** era stato detto e non **chi** l'aveva detto: la
provenance del singolo claim veniva chiesta all'LLM e buttata via dal write
path, quindi ogni attribuzione a valle era una ricostruzione dal testo.

Otto sintomi diversi, una causa comune:

| Sintomo V3 | Dove nasceva |
|---|---|
| affermazione attribuita alla persona sbagliata | `mirror` scartava `source_name`, `kg_claim` non aveva `attributed_to` |
| accordo dichiarato fra due fonti su un punto di una sola | nessuno contava le fonti: `status="confirmed"` era un'opinione del modello |
| audit "claim → fonte → estratto" risolto con una nuova sintesi | nessuna colonna teneva il passaggio verbatim, nessun tool lo restituiva |
| linguaggio forte su fonte singola | il grado di sostegno non esisteva come dato |
| "non conosco la policy" diventato contraddizione | un solo tipo di divergenza disponibile |
| informazione registrata dichiarata mancante | i claim vivevano solo nello stato del turno |
| testimonianza di un reparto estesa al processo | nessun campo di perimetro sul claim |
| sintesi più forte del testo | nessun riscontro della citazione sul sorgente |

Il follow-up ha aggiunto un nono sintomo, di natura diversa — **composizione**:
la corroborazione si contava sul *soggetto*, quindi due fonti che parlavano di
autorizzazione risultavano concordi *sull'autorizzazione*, e la sintesi ne
scriveva una frase sola attribuita a entrambe, ereditando proprietà che ne
aveva detta una.

## Le tre unità che il modello dati ora tiene separate

```
topic       il SOGGETTO          "autorizzazione della spesa"
assertion   la PROPOSIZIONE      "sopra soglia serve un'autorizzazione"
qualifiers  gli ATTRIBUTI        "verifica formale prima dell'ordine"
```

- Parlare dello stesso **soggetto** non è concordare. Il soggetto serve a
  mettere vicino ciò che si assomiglia.
- La corroborazione si conta sulla **proposizione**. Due claim corroborano solo
  se dichiarano la stessa `assertion` e vengono da due voci distinte. Senza
  `assertion` si ricade sull'enunciato: fail closed, due formulazioni diverse
  restano due affermazioni.
- Gli **attributi** appartengono alla voce che li dice. Il nucleo condiviso di
  un gruppo è l'intersezione, mai l'unione: è unendo che la regola di una fonte
  finiva in bocca a due.

A questo si aggiungono, sempre sul claim: `attributed_to` (chi parla dentro la
fonte, distinto da `source_name` che è il documento), `quote` +
`quote_verified`, `scope_label` + `scope_level`, `epistemic_status`.

## Le invarianti, e chi le fa rispettare

Tutte in `backend/memory/provenance.py`. Nessuna chiama un LLM, nessuna tocca
il database: sono funzioni pure, quindi verificabili senza infrastruttura.

1. **`quote_is_grounded(quote, source_text)`** — una citazione esiste nel testo
   della fonte o non è una citazione. Confronto normalizzato, poi senza
   punteggiatura: ricopiare togliendo una virgola resta ricopiare, riscrivere
   più forte no. Applicata in `canonical.write_evidence` (che scrive
   `quote_verified`) e in `extract_process_claims`.
2. **`build_ledger(claims)`** — il grado di sostegno è **calcolato**, non
   dichiarato: `corroborated` / `single_source` / `contradicted` / `inferred` /
   `declared_unknown`, contando le voci distinte sulla stessa proposizione. Chi
   dichiara di non sapere non corrobora e non è una lacuna.
3. **`shared_core(claims)` / `verify_shared_statement(text, claims)`** — una
   frase attribuita a più voci può contenere solo ciò che tutte reggono. Il
   controllo è deterministico perché gli attributi sono *dichiarati sul claim*,
   non dedotti dal testo: se un attributo esclusivo compare nella frase
   condivisa, la composizione è invalida e il tool dice di chi è.
4. **`classify_divergence(declared, stances)`** — può solo **declassare**. Meno
   di due voci → non è una divergenza; una parte che dichiara di non sapere →
   al massimo lacuna di conoscenza; perimetri diversi → al massimo differenza
   di ambito. Solo ciò che resta `incompatible` blocca la modellazione.
5. **`verify_corroboration(...)`** — "le due fonti concordano" è verificabile:
   si contano. Include il controllo di composizione e il guardrail sulla
   generalizzazione (una conclusione dichiarata valida per l'intero processo
   ma sostenuta solo da voci di reparto viene riportata al suo perimetro).
6. **`audit_answer(text, ledger)`** — lo stesso controllo, ma sulla **prosa
   consegnata**. Una frase che nomina due voci, o che dichiara un accordo
   ("più fonti concordano", "entrambi"), non può contenere un attributo che il
   registro assegna a una sola. Il nodo che scrive la risposta chiede una
   correzione, una volta; se la prosa resta fusa, il runtime allega
   `render_attribution_notice` e dice di chi è cosa.
7. **`exact_span` / `excerpt_around`** — ciò che finisce fra virgolette è il
   testo della fonte, ritagliato con i suoi caratteri. Il confronto avviene su
   una proiezione normalizzata che conserva la mappa verso gli offset
   originali, quindi il verbatim non è mai una versione ripulita.

### Perché il punto 6 esiste

Il primo giro aveva messo il controllo di composizione dentro
`synthesize_process_evidence`. Non basta: quel tool l'agente può non chiamarlo,
e la prosa finale la scrive un altro nodo. La frase multi-fonte si riformava
all'ultimo passaggio, dove nessuno la guardava più. Un'invariante vale dove
sta il testo che il consulente legge.

### Perché il punto 7 esiste

`quote` era la copia che l'estrattore aveva ricopiato, e l'audit ritagliava
sul testo *normalizzato*: fra virgolette compariva una versione minuscola e
ripulita — o, peggio, una riformulazione. Ora il passaggio viene ancorato al
sorgente **in scrittura** (`write_evidence`, `extract_process_claims`) e
sostituito con la sottostringa reale; quando non si ancora, il renderer non lo
virgoletta affatto e dichiara che è una riformulazione.

## Il percorso dei dati, dopo la fix

```
intervista in chat
  └─ manage_process_evidence(save_interview)      claim con provenance completa
       ├─ episodic_store                          custodia del testo grezzo
       └─ mirror.mirror_evidence                  NON scarta più i campi
            └─ canonical.write_evidence           verifica la citazione,
                 ├─ kg_claim (0015 + 0016)        scrive attributed_to/quote/
                 │                                 scope/assertion/qualifiers
                 └─ graph_outbox → Neo4j          solo gli enum (INV-5 / B+)

lettura
  gateway.claim_ledger      claim in scope + support CALCOLATO
  gateway.graph_retrieve    ogni claim nel contesto porta la sua voce
  manage_process_evidence(ledger|provenance)      registro / audit verbatim

turno di chat
  load_process_context → evidence_ledger          l'evidenza già raccolta
  process_report        prosa dal registro
                        → audit_answer            una correzione, poi la nota
                        → "Da dove viene"         sezione STAMPATA dal runtime
```

L'ultimo passaggio è il punto: la prosa la scrive il modello, la tracciabilità
no. La sezione "Da dove viene" è resa dal runtime a partire dal registro, riga
per riga, con la voce, il grado di sostegno, l'ambito, la citazione e — per un
gruppo corroborato — ciò che aggiunge solo una delle voci.

## Cosa resta affidato al modello

Il runtime garantisce che il registro sia corretto, che il grado di sostegno
sia calcolato, che fra virgolette finisca solo testo della fonte, che una
composizione indebita venga rifiutata sia dal tool di sintesi sia sulla prosa
consegnata, e che l'audit risponda con il testo originale.

Resta affidato al modello **come sono formulate le frasi**. Il controllo
sull'output riconosce l'attribuzione multipla e gli attributi *dichiarati*: se
l'estrattore non mette in `qualifiers` ciò che una sola fonte aggiunge, quel
pezzo non è verificabile e il controllo non lo vede. La qualità
dell'estrazione è quindi il limite superiore della garanzia — motivo per cui i
`qualifiers` sono richiesti nello schema del claim e non lasciati opzionali
nella pratica.

## Dove guardare

| Cosa | File |
|---|---|
| invarianti | `backend/memory/provenance.py` |
| schema claim (tool) | `backend/memory/knowledge_graph/models.py`, `backend/graphs/process/subgraphs/evidence/tools.py` |
| scrittura | `backend/memory/knowledge_graph/mirror.py`, `.../canonical.py` |
| lettura | `backend/memory/gateway.py` (`claim_ledger`, `_hydrate`) |
| audit / registro | `backend/toolsets/process_memory.py` (`ledger`, `provenance`) |
| registro per i prompt | `backend/agents/evidence_brief.py` (`turn_evidence_ledger`, `render_ledger_lines`, `evidence_prompt_block`) — una resa sola, letta dal prompt di scope, dal router e dalla risposta |
| risposta | `backend/graphs/process/graph.py` (`build_process_report`) |
| migrazioni | `migrations/versions/0015_claim_provenance.py`, `0016_claim_assertion_qualifiers.py` |
| test | `tests/test_evidence_provenance.py`, `tests/test_evidence_composition.py`, `tests/test_answer_composition.py`, `tests/test_process_evidence_provenance_e2e.py`, `tests/test_process_evidence_to_plan.py` |
| fonte leggibile per intero | `backend/workspace_services/source_document.py`, `frontend/src/features/projects/components/SourcesPanel.tsx` |

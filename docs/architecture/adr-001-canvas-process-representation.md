# ADR-001: rappresentazione dei processi nell'agente canvas

Data: 24 novembre 2026
Stato: **accettata come direzione architetturale; attivazione del DSL per scritture agentiche bloccata dai gate sotto**

## Contesto e decisione

DeliR deve generare e modificare processi in modo rapido senza perdere
informazioni aziendali o alterare parti non richieste. I benchmark locali
mostrano che il DSL DeliR v1 e' meno compatto di TOK, ma conserva integralmente
l'albero semantico dei tre BPMN provati; TOK non lo fa su quegli stessi file.
BPCF e' promettente per la generazione, ma non abbiamo una conversione
controllata dei BPMN DeliR verso il formato ufficiale. Nessun confronto LLM
end-to-end e' stato ancora eseguito.

**Scelgo l'architettura DeliR a tre rappresentazioni, con responsabilita'
distinte:**

1. **Fonte del significato:** evidenze, ProcessUnderstanding, decisioni
   confermate e BPMNSemanticModel versionati. Il modello linguistico non
   inventa decisioni mancanti.
2. **Formato canonico e di interoperabilita':** BPMN 2.0.2 XML, con diagram
   interchange (DI) nel canvas e versioning nel database. Il formato compatto
   non sostituisce il BPMN salvato.
3. **Vista compatta dell'agente:** per le modifiche locali, la mappa di
   navigazione di sola lettura (`backend/bpmn/compact_canvas_map.py`) mostra
   ID, etichette, lane e archi; il BPMN completo rimane nel runtime. L'agente
   applica operazioni atomiche sul modello canonico, senza rigenerarlo.
   DeliR DSL v1/v2 (`backend/bpmn/compact_representation.py`) restano codec
   sperimentali per i casi che richiedono una rappresentazione autonoma.

Il DSL e' **scelto come candidato interno prioritario**, non attivato come
formato di scrittura LLM in produzione. Una versione successiva potra'
codificare un grafo BPMN tipizzato invece dell'attuale albero XML compatto,
ma dovra' passare gli stessi gate. BPCF-Full con prompt/validazione strict e TOK restano comparatori nel
benchmark; JSON Branches e Mermaid sono comparatori di leggibilita' e
compattezza, non sorgenti canoniche. Nessun codice TOK GPL viene incorporato.

## Confine OMG e gate di accettazione

La specifica di riferimento e' [OMG BPMN 2.0.2](https://www.omg.org/spec/BPMN/2.0.2/).
Gli [XSD pubblicati da OMG](https://www.omg.org/spec/BPMN/machine-readable)
sono il gate di interoperabilita' XML. Passare lo schema non prova tutte le
regole semantiche BPMN, la soundness o la fedelta' al processo.

| Livello | Gate per una proposta agentica | Stato corrente |
| --- | --- | --- |
| L1 Syntax | Parser del formato compatto, schema/versione, riferimenti e input completi; errore senza modifica se non supportato | Codec DeliR v1 e controlli di struttura presenti |
| L2 BPMN conformance | Compilazione a XML, XSD OMG 2.0.2, riferimenti e regole semantiche implementate | Gate XSD e validazione locale attivi per nuove scritture agentiche e approvazioni; i diagrammi legacy non conformi ammettono solo edit locali senza nuovi errori XSD |
| L3 Behavioral soundness | Raggiungibilita', uscite, gateway; per deadlock/concorrenza serve analisi token-based o dichiarazione del limite | L'analizzatore del BPMNSemanticModel era gia' presente. Il BPMN XML effettivo passa controlli di raggiungibilita' del grafo principale e un gioco dei token limitato (gateway esclusivi, paralleli ed event-based, attivita', eventi, boundary, terminate): rileva join paralleli che attendono per sempre, passaggi raggiunti due volte dalla stessa pratica e esecuzioni che non terminano. Le scelte esclusive sono libere (astrazione classica della soundness): un deadlock trovato e' possibile per alcuni dati. Gateway inclusivi/complessi, uscite condizionali da attivita' e superamento del budget di stati sono dichiarati fuori ambito nel report, non promossi a "sound"; i subprocessi sono atomici. Costruzioni complete e review approvate vengono rifiutate prima della scrittura; le modifiche locali restano bozze. |
| L4 Semantic fidelity | Tracciabilita' a fonti e decisioni; confronto con piano e revisione umana delle ambiguita' | Controlli parziali; equivalenza alla baseline XML non misurata |
| L5 Modification integrity | Diff semantico contro versione precedente, allowlist delle sole modifiche richieste, ID stabili, scrittura atomica | Gate prima della scrittura del tool canvas per update, add, delete, connect, reconnect, layout e clear. Su Postgres: ogni operazione locale su due fixture passa dal percorso di scrittura vero e l'XML riletto differisce solo per il delta dichiarato; due turni agente dalla stessa versione, in sequenza o in thread concorrenti, scrivono una volta sola. L'eliminazione rimuove anche associazioni, message flow e data association collegate. Restano da coprire i percorsi legacy fuori dal tool canvas. |

Una proposta nuova passa al canvas solo se i gate applicabili sono verdi.
Un import esistente non conforme viene segnalato con il dettaglio preciso:
nessuna conversione silenziosa e nessuna sostituzione parziale del modello.
L1-L5 devono essere registrati separatamente; non comprimere tutto in un
singolo booleano “BPMN valido”. Il livello L3 attuale controlla proprieta'
necessarie ma non la soundness formale di ogni rete di workflow.

## KPI: target e risposta misurata

Definire i rapporti con *stessa richiesta, stesso modello, stesso dataset e
stessa semantica*, usando token effettivi del provider nel turno completo.
Il superamento della soglia vale sul corpus dichiarato, non su un esempio.

| KPI | Target | Stato al 24/11/2026 |
| --- | ---: | --- |
| Riduzione token della rappresentazione | >=85% | **Raggiunto solo per la vista locale incompleta**: mappa di navigazione 88,02% mediano, 55/55 casi alla soglia. Per un documento autonomo reversibile il target resta aperto: DSL v1 76,3%, v2 77,02% su PMo 55, entrambi 55/55 round trip esatti. TOK arriva a 88,8%, ma 0/55 round trip semantici esatti. |
| Riduzione token complessivi per operazione | >=50% | **Sonda: 80,79% mediano** (input+output del provider, tool loop con funzioni di produzione, `gemini-3.5-flash-lite`, 3 casi, 1 ripetizione; `docs/canvas-llm-benchmarks.md`). Esclusi prompt di sistema e schema tool di produzione: la cifra reale sara' piu' bassa. |
| Riduzione token nelle modifiche locali | >=90% | **Non raggiunta sul solo prompt di scope**: con la mappa completa inclusa, riduzione mediana 76,86% su PMo 55 e 0/55 casi alla soglia; senza mappa inline era 87,42%, ma serviva una lettura tool. Sul ciclo di modifica con modello vero la sonda da' 80,79% mediano (vedi riga sopra): sotto la soglia del 90%. |
| Validita' BPMN dei modelli accettati | 100% sui controlli implementati | **Gate L2 attivo per nuovi modelli agentici**, con un fixture conforme e test di rifiuto prima del salvataggio. La copertura complessiva non e' ancora dimostrata: i tre fixture legacy superano il validatore locale ma falliscono l'XSD OMG. |
| Conservazione nel round trip | 100% sui costrutti supportati | **55/55 processi PMo** con albero semantico identico nel codec DeliR; 46/55 sorgenti passano l'XSD OMG e restano conformi dopo la conversione. Restano costrutti BPMN e namespace non coperti. |
| Modifiche collaterali non richieste | 0 | **0 nei 9 patch di rinomina** provati con Postgres; servono anche aggiunte, eliminazioni, reconnessioni e casi concorrenti. |
| Accuratezza semantica | >= baseline XML | **Sonda: pari** sul ciclo di modifica, 3/3 con mappa e 3/3 con XML, 0 violazioni L5. Campione troppo piccolo per una conclusione. |
| Hallucination rate | < baseline XML | **Sonda L4 su 2 casi**: falsi positivi XML 0, DSL v1 0, mappa 1; omissioni piantate trovate XML 1/2, DSL v1 2/2, mappa 2/2. Non basta per confrontare i tassi. |

Il KPI “100%” deve essere il tasso di accettazioni che superano tutti i
controlli implementati; registrare anche la copertura dei controlli e il
tasso di rifiuto. Una validazione piu' severa puo' aumentare i rifiuti senza
peggiorare la qualita' dei modelli accettati.

## Protocollo per la scelta di release

Usare casi accoppiati, ordinamento randomizzato delle rappresentazioni, stesso
modello e budget, ripetizioni e intervalli di confidenza. Separare:

- **Generazione:** [PMo](https://zenodo.org/records/15857589), con 55 coppie
  descrizione/modello e ground truth BPMN; evitare sovrapposizioni con PET.
- **Estrazione da testo:** [PET](https://arxiv.org/abs/2203.04860), con attivita',
  attori, gateway e flussi annotati.
- **Interoperabilita':** [BPMN MIWG](https://github.com/bpmn-miwg/bpmn-miwg-test-suite)
  e XSD OMG, distinguendo metadati/DI da semantica.
- **Modifiche:** [BPMN Assistant Evaluation](https://huggingface.co/datasets/jtlicardo/bpmn-assistant-eval)
  con modelli iniziali e risultati attesi verificati; il dataset pubblico da
  solo contiene richieste testuali, quindi gli input vanno ricostruiti e auditati.
- **DeliR:** casi sintetici e casi reali anonimizzati e autorizzati, con fonti
  e decisioni tracciate; nessun dato cliente grezzo nel repository.

Misurare almeno token di sistema/input/output/cache e tool, numero di chiamate,
latenza p50/p95, parse rate, XSD pass rate, errori BPMN, comportamento,
copertura delle fonti, claim senza fonte, round trip, diff inattesi e tasso
di rifiuto. Il gate di promozione richiede nessuna regressione critica su
L2-L5; poi si ottimizzano i token sulla frontiera di Pareto. Un risparmio di
token non compensa perdita di significato.

## Conseguenze e limiti

Il canvas puo' mantenere interoperabilita' e audit mentre l'agente riduce il
contesto e usa delta. Il codec DeliR e' reversibile sull'albero XML semantico
provato, ma non codifica DI e rifiuta contenuto XML misto. I prefissi usati
nei valori QName (`xsi:type`, `messageRef`) sono conservati: le dichiarazioni
necessarie viaggiano sulla radice e i test confrontano i QName risolti, non
solo l'albero. Un prefisso legato a due namespace resta rifiutato. La generazione LLM e il confronto BPCF/TOK
restano da eseguire; l'ADR non trasforma quei risultati mancanti in successi.

Evidenza locale: `docs/canvas-representation-benchmark.md`,
`docs/canvas-patch-performance-baseline.md`,
`tests/evals/l0_deterministic/test_canvas_representations.py`,
`tests/bpmn/test_omg_conformance.py`,
`tests/bpmn/test_canvas_edit_integrity.py`.

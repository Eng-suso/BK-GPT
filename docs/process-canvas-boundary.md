# Process Agent → Canvas Agent

Chi possiede cosa, cosa attraversa il confine, e perche' il Canvas non puo'
diventare una seconda fonte di verita'.

## Il problema

La Process Chat sapeva chi aveva detto cosa: tre interviste, le voci separate,
il grado di sostegno di ogni affermazione, le lacune ancora aperte. Il planner
del canvas, con le stesse tre interviste agli atti, dichiarava di conoscere
"esclusivamente il titolo del processo" e ripartiva a chiedere trigger, attori e
prima attivita'.

Non era un difetto del canvas. Fra i due agenti passava il solo `bpmn_model_id`:
il Canvas riapriva il database per conto suo, leggeva il `BPMNSemanticModel`
della review, e tutto il resto se lo ricostruiva dal testo della chat. Tre cose
mancavano, e sono tre cose diverse:

1. **la conoscenza non attraversava.** Fonti, claim con provenance, divergenze,
   decisioni gia' prese dal consulente: niente di tutto questo arrivava di la';
2. **non esisteva una versione.** "Questo disegno e' stato costruito su quale
   stato del processo?" non era una domanda a cui si potesse rispondere male:
   il dato proprio non c'era;
3. **il Canvas poteva scrivere la verita'.** `prepare_canvas_bpmn_review`
   accetta prosa libera e ricostruisce da li' la `ProcessUnderstanding`. Due
   passaggi, e il disegno diventava la fonte e le interviste un ricordo.

## La divisione

```
INTERVISTE / DOCUMENTI / CHAT
          |
     PROCESS AGENT              <- possiede la conoscenza del processo
     evidence, claims, gaps
     contraddizioni, unknowns
     ProcessUnderstanding
     confidence + provenance
          |
  PROCESS KNOWLEDGE SNAPSHOT    <- il confine: versionato, deterministico
          |
      CANVAS AGENT              <- possiede la trasformazione in BPMN
      semantic mapping
      topologia BPMN 2.0
      validazione + layout
          |
      BPMN DRAFT
```

Il Process Agent possiede la comprensione del processo. Il Canvas Agent possiede
la trasformazione di quella comprensione in eventi, task, lane, gateway,
sequence flow ed exception path. Il Canvas non riscopre il processo, il Process
Agent non disegna.

## Lo snapshot

`backend/agents/process_snapshot.py`. Deterministico, in sola lettura, senza
LLM. E' l'unico oggetto che attraversa il confine.

Contiene identita' (`process_id`, `bpmn_model_id`, `version`, `snapshot_id`,
`evidence_source_set_id`), conoscenza canonica (`ProcessUnderstanding`,
`BPMNSemanticModel`), evidenza (fonti, registro dei claim con voce e sostegno,
`ledger_summary`), cio' che non si sa (`open_questions` con alternative e
risposte, `missing_information`) e quanto e' pronto (`draft_readiness`,
`validation_readiness`, `readiness_score`).

**L'identita' si calcola, non si dichiara:**

```python
snapshot_id = sha256(process_id, review.version, evidence_source_set_id)[:16]
```

Tre ingredienti e nessun altro. Due letture dello stesso stato danno la stessa
identita'; una risposta del consulente o una fonte in piu' ne danno una diversa,
perche' in entrambi i casi il processo sa qualcosa che prima non sapeva.

Non entra la proiezione dei claim nel knowledge graph: e' asincrona e puo'
degradare, e farla entrare significherebbe dichiarare "conoscenza cambiata" ogni
volta che la proiezione e' indietro - la stessa oscillazione che il registro
dell'evidenza aveva gia' dovuto togliere di mezzo. Lo stato della proiezione
viaggia comunque dentro lo snapshot (`claim_status`), dichiarato: chi legge sa
se la provenance e' completa o solo in ritardo.

`snapshot.label` e' la versione come la si nomina in una frase: `V17`.

## Il runtime agentico del Canvas

Il Canvas non riceve una fotografia una volta sola. Ha due tool verso la
knowledge authority, e li usa quando decide lui:

| tool | cosa fa |
| --- | --- |
| `inspect_process_knowledge(process_id)` | rilegge lo snapshot autoritativo, con provenance, lacune e decisioni gia' prese |
| `raise_modeling_question(...)` | rimanda indietro **una** decisione che lo snapshot non regge |

La regola che rende agentico questo senza creare una seconda verita' e' una
sola: **il Canvas puo' leggere e puo' chiedere, non puo' concludere.**

Il loop:

```
utente: "Genera BPMN"
  -> Canvas legge lo snapshot V17
  -> costruisce, valida, ripara
  -> trova un'ambiguita' che cambia davvero la topologia
  -> raise_modeling_question  ->  la domanda entra nel Process IR, V17 -> V18
  -> il run termina waiting_for_user (non "fatto", non "fallito")
utente risponde
  -> answer_bpmn_review_question  ->  V18 -> V19
  -> Canvas riprende da V19
```

Una domanda registrata cosi' non e' una nota del canvas: e' un `unknown` del
piano, con le sue alternative, e arriva al consulente nella card che gia'
esiste (`ReviewQuestionsCard`). La risposta e' conoscenza del processo, non un
messaggio di chat.

**Il run dichiara come e' finito.** `canvas_run_status` vale `done`,
`waiting_for_user` o `failed`; il `validation_report` porta
`process_snapshot_id` e `process_snapshot_label`, quindi "il canvas e'
aggiornato" smette di essere un'affermazione senza referente.

## Le tre porte chiuse

1. **Il piano non puo' ignorare l'evidenza.**
   `assert_plan_respects_evidence` rifiuta una review senza attori, partecipanti
   ne' attivita' mentre il processo ha fonti agli atti. Vale sia per il tool di
   modeling sia per `prepare_canvas_bpmn_review` / `prepare_process_bpmn_review`,
   che ricostruiscono la `ProcessUnderstanding` da prosa libera. Prima il
   controllo viveva solo nel modeling, e quella era la porta di servizio.

2. **Il Canvas non puo' introdurre un tema che le fonti non hanno mai nominato.**
   Una `raise_modeling_question` non ancorata all'evidenza viene scartata dal
   filtro di grounding che gia' governa le domande del piano, e il tool lo dice:
   `status = dropped_not_grounded`.

3. **Un disegno costruito su una versione superata non si chiude.**
   `knowledge_drift` confronta la versione su cui il run e' partito con quella
   corrente. Se sono diverse, il run va in `waiting_for_user` invece di salvare:
   un disegno corretto su conoscenza superata resta un disegno da rifare.

## I test

`tests/test_process_canvas_handoff_e2e.py` — quattro invarianti, deterministiche,
su database vero:

- **handoff completeness**: Laura, Paolo e Francesca arrivano dall'altra parte
  con le loro voci e la lacuna che nessuno copre;
- **semantic reconstruction**: da quello snapshot esce un BPMN che regge la
  validazione contro il piano, con una corsia per attore, la decisione come
  gateway e il percorso urgente agganciato;
- **version refresh**: una risposta cambia la versione, e il canvas legge la
  nuova; una proiezione dei claim degradata non ne inventa una;
- **no parallel truth**: i due lati leggono lo stesso `snapshot_id`; il canvas
  non riscrive il piano da prosa; la sua domanda finisce sul processo; un run su
  versione superata si ferma.

`tests/evals/` — agent eval con LLM reale, spento per default:

```bash
DELIR_AGENT_EVAL=1 uv run pytest tests/evals -q -s
```

Fa mappare l'AS-IS all'agente vero dalle tre interviste e lo giudica con una
rubrica **deterministica** (`tests/evals/rubric.py`): un eval giudicato da un
secondo LLM misura l'accordo fra due LLM, che non e' cio' che serve sapere prima
di mostrare una mappa a un cliente.

La rubrica divide i criteri in due famiglie, e la differenza fra le due e'
l'unica cosa che conta davvero:

- **completezza** — i tre reparti, il lavoro di ognuno, la decisione sulla
  soglia, il percorso urgente, l'inizio e la fine;
- **onesta'** — nessun attore inventato, nessun passaggio inventato, la lacuna
  che nessuno copre resta una domanda, il flusso di controllo e' sano.

I criteri di onesta' sono obbligatori. Un modello incompleto e' incompleto; un
modello disonesto e' un AS-IS che il cliente firmerebbe credendo che descriva la
sua azienda.

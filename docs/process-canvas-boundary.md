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

## Cio' che mancava ancora: il piano non esisteva

Il confine descritto qui sotto era costruito, e il difetto restava. Il motivo si
vede solo misurando lo stato in cui il consulente lavora davvero: tre interviste
salvate, e nessuno che abbia preparato un piano.

```
fonti: 3   claim: 0   modello semantico: assente   modelable: no
prerequisiti mancanti per process.canvas_handoff:
    ['bpmn_semantic_model', 'readiness_for_canvas']
```

La `ProcessUnderstanding` vive dentro la review BPMN, e la review esiste solo se
qualcuno la prepara. Prepararla era **un passo dell'agente**: il router doveva
scegliere `modeling`, il subagente doveva chiamare
`prepare_process_understanding_review`, e doveva riempirne bene l'argomento. Tre
condizioni affidate a un prompt, per un'invariante che invece e' dura:

> se il processo ha evidenza agli atti, il processo ha un piano.

Quando quel passo non avveniva il gate rifiutava per prerequisito mancante, il
turno finiva in chiarimento, e al consulente arrivavano le domande da
questionario su trigger, attori e prima attivita' — dopo tre interviste che quei
punti li avevano descritti. "Nessuna intervista disponibile", "nessun attore", il
modello start → end e le domande generiche non erano quattro difetti: erano un
difetto solo, e non era nel Canvas. La conoscenza non si perdeva nel passaggio,
non era mai stata sintetizzata.

`backend/agents/process_synthesis.py` fa di quel passo un fatto del confine.
`ensure_process_plan(process_id)` gira dentro `delegate_to_canvas_macro`, prima
che il Canvas parta, ed e' deterministico su **quando** sintetizzare:

| stato | azione |
| --- | --- |
| piano assente, evidenza agli atti | `synthesized` — il piano nasce dal corpus delle fonti |
| piano costruito su un set di fonti diverso | `synthesized` — una quarta intervista non lascia in piedi un piano di tre fonti fa |
| piano gia' costruito sulle fonti correnti | `reused` — rifarlo cancellerebbe le risposte del consulente |
| nessuna evidenza | `no_evidence` — il Canvas non parte, e si dice perche' |
| estrazione fallita | `synthesis_failed` — un guasto, raccontato come guasto |

Il piano dichiara le fonti su cui e' nato (`evidence_source_set_id`, colonna
aggiunta dalla migration `0008`). Senza quel dato "il piano e' aggiornato rispetto
alle interviste?" non era una domanda a cui si potesse rispondere. Una review
preparata prima che la colonna esistesse dichiara `NULL`, che significa "non si
sa": con evidenza agli atti va risintetizzata, perche' l'alternativa e' fidarsi
di un piano che potrebbe ignorare un'intervista.

Le due soglie restano due, ed e' il punto che il difetto schiacciava:

| soglia | quando | cosa autorizza |
| --- | --- | --- |
| `draft_readiness` | `synthesizable` con evidenza, `modelable` con un piano | disegnare una bozza con le lacune dichiarate dentro |
| `validation_readiness` | `ready_for_approval` solo a lacune chiuse | dichiarare l'AS-IS validato |

`None` non era una risposta: chi lo leggeva lo trattava come "non modellabile", e
un processo con tre interviste diventava indistinguibile da un processo di cui non
si sa niente.

Lo snapshot, infine, porta **il testo** delle fonti e non i loro nomi. La
proiezione dei claim e' asincrona — nella prova reale valeva zero claim su tre
interviste — e in quella finestra dall'altra parte del confine arrivavano tre nomi
e nessuna sostanza.

## Due artefatti, non uno

Il confine descritto sotto separa due *proprietari*. Ne mancava un altro, dentro
il Process Agent: la separazione fra i due **artefatti**.

```
MODELING PLAN                          BPMN DRAFT
partecipanti, corsie candidate,        eventi, task, lane, gateway,
attivita', flusso, decisioni,          sequence flow, exception path,
percorsi di eccezione, evidenza        layout, DI
a sostegno, incertezze, lacune
                                       si genera dal piano approvato
si genera, si modifica, si versiona,
si riapre, si approva
        |                                        |
"mettilo nel piano"                    "genera / applica il BPMN"
```

Non erano separati. `CAPABILITY_REGISTRY` aveva la capability che prepara il
piano e quella che consegna al canvas, ma niente diceva *quale artefatto* una
richiesta modifica: la scelta era implicita nella route che il modello proponeva,
e "mettilo nel piano" poteva finire su `delegate_canvas` senza che niente lo
fermasse. Il consulente se ne accorgeva dalla risposta - una richiesta di
cambiare modalita' per disegnare, dopo aver chiesto di scrivere.

Il difetto misurato era questo, e sono cinque cose diverse:

| cosa si vedeva | dov'era |
| --- | --- |
| "mettilo nel piano" chiedeva la modalita' per costruire il canvas | l'intento non sceglieva l'artefatto |
| il piano si poteva solo rifare da capo | nessuna operazione di amend |
| l'As-Is ricco tornava a essere qualche bullet | ogni scrittura sostituiva il piano intero |
| il piano riletto era identico a prima | la scrittura non partiva, e il rifiuto non lo diceva |
| un piano collassato usciva come "completato" | il piano non aveva un loop di review |

### L'artefatto lo dichiara l'intento, l'accoppiamento lo rompe il runtime

`ProcessRoutingDecision.target_artifact` vale `modeling_plan`, `bpmn_canvas` o
`none`, e ogni `CapabilitySpec` dichiara l'artefatto che tocca. Classificare
l'intento resta lavoro del modello - e' quello il lavoro. Cio' che il runtime
toglie di mezzo e' l'accoppiamento: `authorize_routing_decision` rifiuta una
capability che modifica un artefatto diverso da quello dichiarato
(`artifact_route_mismatch`), e `misdirected_plan_request` reinstrada su
`process.plan_edit` una richiesta sul piano finita sul canvas. Il nodo di delega
tiene l'ultima porta: `target_artifact == "modeling_plan"` non attraversa il
confine verso il disegno.

### Il piano si modifica, e modificarlo non cancella

`backend/agents/process_plan.py`. Due operazioni, una sola regola di scrittura:

| operazione | cosa fa |
| --- | --- |
| `amend` | il piano corrente **piu'** cio' che arriva. Cio' che non viene ripetuto resta |
| `replace` | il piano viene rifatto da capo. Esplicito, mai implicito |

Il merge e' deterministico e non chiede niente all'LLM: le liste si uniscono per
identita' stabile (l'`id`, o l'etichetta quando un rigenerato ha rinumerato), e
le voci omonime si fondono campo per campo. Un campo assente non e' una
cancellazione, e' silenzio - se lo fosse, ogni emendamento parziale cancellerebbe
il piano intorno a se', e una dimenticanza del turno diventerebbe una lacuna del
processo. I percorsi ordinati (`sequence`, `main_success_path`) fanno eccezione:
li' l'ordine *e'* l'informazione, quindi chi ne dichiara uno lo sta riordinando e
chi tace lo lascia com'era.

Le note su cui il piano nasce sono le fonti, non il riassunto della modifica. Non
e' cosmetica: il filtro di ancoraggio giudica le domande del piano contro quel
testo, e un piano preparato su una riga di riassunto si vedeva scartare le
proprie lacune come "non ancorate all'evidenza".

Una modifica al piano **non tocca il diagramma** e non richiede una modalita' di
canvas. Applicare il piano al disegno e' una richiesta diversa.

### Il piano si fa rivedere

Il Canvas aveva un loop di verifica - disegna, confronta col piano, ripara,
riconfronta - e il piano non ne aveva nessuno: `evaluate_process_iteration`
guarda una firma di progresso, che dice se lo stato *e' cambiato*, non se cio'
che c'e' ora e' un piano utilizzabile. Un piano collassato a inizio e fine
usciva come "passata completata" e arrivava al disegno cosi'.

`evaluate_plan_review` rilegge il piano **dal database** e lo giudica in modo
deterministico (`review_process_plan`): nessuna attivita', nessun attore, un
flusso che cita passaggi che il piano non definisce, attivita' agganciate a
nessun percorso, attivita' senza responsabile. I difetti tornano al subagente di
modellazione con l'elenco; una passata che ripropone gli stessi difetti non ne
consuma un'altra, perche' un loop che non puo' finire e' peggio del difetto che
chiude.

La distinzione fra `issues` e `warnings` regge il loop. Una voce sentita nelle
fonti che il piano non nomina e' un avviso, non un difetto: puo' comparire come
ruolo invece che come nome, e farla guidare il loop lo farebbe girare su una cosa
che nessuna passata puo' chiudere.

### La modalita' che serve la calcola il runtime

Il rifiuto per modalita' diceva all'agente «di' all'utente quale modalita'
servirebbe», e *quale* lo sceglieva il modello - di solito la piu' larga. Con la
chat in Conversazione, il piano si scrive in Piano e il disegno si tocca da
Modifica in su: chiedere Modifica per scrivere sul piano e' la risposta che il
consulente riceveva. `narrowest_mode_for` calcola la modalita' meno ampia che
sblocca la capability rifiutata, e il messaggio di ri-decisione la nomina. Lo
stesso vale sulla scrittura: `assert_write_allowed` dice quale modalita' basta
per *quella* operazione.

Lo stato della modalita' viene dal runtime e ora entra nel contesto del router
(`runtime_chat_mode`). Un "si', fatto" dell'utente non e' una fonte su quale
modalita' e' attiva.

### Cio' che la review del codice ha trovato dopo

Sette difetti della stessa famiglia, trovati rileggendo il lavoro intero invece
dei soli pezzi nuovi. Sono tutti casi in cui un controllo esisteva e non copriva
il percorso su cui il difetto passava:

1. **il gate si aggirava da solo.** La sostituzione di una richiesta sul piano
   instradata sul canvas asseriva route, capability e termination a mano: una
   capability che nessuno aveva autorizzato partiva perche' il runtime l'aveva
   scelta. Ora la sostituzione ripassa da `authorize_routing_decision`, e un
   rifiuto per modalita' o per prerequisito resta il rifiuto che il consulente
   legge.
2. **il controllo di verificabilita' spariva al secondo tentativo.**
   `_unverifiable_completion_issues` leggeva `canvas_route`, che il loop di
   correzione riscrive in `patch_edit`: una costruzione non verificabile al primo
   giro diventava, al secondo, una costruzione senza issue - cioe' completata.
   Ora legge `canvas_initial_route`, che e' come il run e' nato.
3. **il default di route riapriva il cerchio.** Una route `modeling` proposta
   senza nome cadeva su `process.modeling`, che pretende
   `process_understanding`: la capability che richiede il piano per poter
   scrivere il piano. Il default e' ora quella che pretende meno.
4. **una lacuna bloccante non bloccava.** Le scorciatoie della soglia bozza
   (`modelable`, `synthesizable`) uscivano dal gate prima del controllo sulle
   lacune: una lacuna che l'agente aveva classificato bloccante apriva il canvas.
   "Bloccante" e' la parola con cui l'agente dice che senza quella risposta il
   disegno sarebbe un'invenzione.
5. **la provenance del piano si cancellava da sola.** I tool che ricostruiscono
   la review da prosa chiamano `prepare_bpmn_review` senza il set di fonti, e
   `None` azzerava `evidence_source_set_id`: il piano diventava di provenienza
   ignota e veniva risintetizzato a ogni giro. "Non e' stato detto" e "nessuna
   fonte" sono due cose, e ora sono due valori.
6. **il read-after-write verificava una versione e ne raccontava un'altra.** Il
   report usava l'oggetto del writer, non quello riletto. Verificare per poi
   riportare altro e' verificare per finta. Gli stessi due tool non chiedevano
   nemmeno che la versione salisse.
7. **il lato lettura aveva lo stesso difetto del lato scrittura.** `review: null`
   significava "sto leggendo", "la lettura e' fallita" e "il processo non ha un
   piano", e la UI diceva sempre la terza - con accanto un bottone che propone di
   costruire un piano che potrebbe esistere, e costruirlo lo sovrascriverebbe.
   Non dichiarare salvato cio' che non si e' riletto ha un gemello: non
   dichiarare assente cio' che non si e' riusciti a leggere.

## Disegnare e' un comando, non una conversazione

Il confine descritto qui sotto era costruito e il disegno restava lento. La
catena che «Genera BPMN» attraversava era questa, misurata:

```
router di scope -> router di processo -> sintesi del piano (3 chiamate)
  -> router del canvas -> subagente di costruzione (6-8 chiamate, 5-7 tool)
  -> subagente di layout -> subagente di validazione -> loop di correzione
```

Dodici-venti chiamate al modello in sequenza per produrre un XML che il
compilatore sa gia' produrre da solo, con `model_timeout_seconds=45` e un retry
per ognuna. Nessun budget: il ciclo agente -> tool -> agente finiva quando il
modello smetteva di chiedere tool, cioe' quando **il modello** decideva di aver
finito. E poteva finire con una domanda invece che con un disegno: il canvas
registrava una `raise_modeling_question`, la versione del piano saliva,
`knowledge_drift` vedeva la deriva e il run si chiudeva `waiting_for_user`
senza salvare niente - il disegno di quel giro buttato, e al giro dopo l'agente
in attesa della propria domanda.

`backend/workspace_services/bpmn_draft.py` rende la stessa operazione un comando:

```
snapshot -> compile -> validate -> (max 1 repair) -> layout -> persist
         -> read-after-write
```

Zero chiamate al modello quando il piano e' materializzato, zero Mem0, zero
Neo4j - sono proiezioni, e una proiezione lenta non e' una ragione per non
disegnare. Tre regole che il comando non negozia:

| regola | cosa significa |
| --- | --- |
| la richiesta e' l'autorizzazione | nessuna seconda conferma, nessun `waiting_for_user` per una lacuna: cio' che resta aperto esce in `pending_verification` **accanto** al disegno |
| un guasto si racconta come guasto | `reason_code` su cui decidere, non una sottostringa da indovinare. Mai «mancano evidenze» davanti a un errore tecnico |
| niente salvato senza rilettura | vale qui come nel resto del confine |

Ogni fase e' misurata (`load_snapshot_ms` ... `read_after_write_ms`, piu'
`llm_calls`, `tool_calls`, `repair_count`, `process_snapshot_version`): «dove se
ne vanno i secondi» e' una domanda con una risposta numerica.

Il router del canvas dichiara ora **che tipo** di costruzione propone, perche'
un percorso veloce che si prende anche il lavoro sbagliato e' peggio di un
percorso lento:

| `construction_kind` | chi lo esegue |
| --- | --- |
| `full_from_plan` | il comando deterministico |
| `partial_change` | il subagente: rigenerare tutto per cambiare un pezzo cancella il lavoro intorno |
| `from_user_description` | il subagente: li' il piano va ancora costruito |

### Un agente ha un tetto

`backend/graphs/agent_budget.py`. Tre limiti, perche' i modi di non finire sono
tre: passi di decisione, chiamate a tool, scadenza del turno. Il controllo sta
**prima** della decisione, dove fermarsi lascia un transcript coerente: fermarsi
dopo aver emesso una tool call lascerebbe una chiamata senza risposta nel
checkpoint, e il turno successivo partirebbe da uno storico che il provider
rifiuta.

Il budget vive in `ConversationState`, quindi e' condiviso fra i subagenti di
uno stesso scope - tre passate da N passi non sono tre budget - e **non** in
`ConsultantState`, che e' lo schema persistito: se ci fosse, ogni thread
arriverebbe al proprio tetto una volta sola e poi ogni turno nascerebbe gia'
scaduto.

## Il piano si materializza quando cambia la conoscenza

La sintesi del piano costa chiamate al modello, e viveva dentro il percorso
critico del disegno - cioe' nel momento in cui qualcuno guarda lo schermo e
aspetta. Il lavoro appartiene al momento in cui l'evidenza cambia.

Salvare una fonte mette il processo in coda
(`workspace_plan_materializations`, migration `0009`) **nella stessa
transazione della fonte**: se il salvataggio torna indietro, la richiesta di
ricostruzione torna indietro con lui. `backend/workers/plan_worker.py` la lavora
chiamando `ensure_process_plan` - la stessa funzione del confine, non una
seconda strada per costruire un piano - dentro il tenant che la riga dichiara.

Una riga per processo, non una per evento: cinque interviste salvate di seguito
sono una sintesi dopo l'ultima. Un guasto momentaneo si riprova con backoff; un
processo che non esiste piu' esce subito, perche' riprovarlo cinque volte dice
la stessa cosa cinque volte.

Quando il comando trova un piano **indietro** rispetto alle fonti, disegna
quello che c'e' e lo dichiara: rifare la sintesi li' rimetterebbe tre chiamate al
modello davanti a chi aspetta, e non disegnare niente sarebbe peggio di un
disegno con una nota.

## Il piano nasce da ogni fonte intera

L'estrazione leggeva un corpus unico, tagliato a 12.000 caratteri per fonte e
30.000 in tutto. Un'ora di intervista sono 40-60.000 caratteri: il piano nasceva
da circa il primo terzo di ognuna, e cio' che veniva raccontato a meta' colloquio
non arrivava mai al disegno. Nessun prompt puo' recuperare un testo che non e'
stato letto, e il taglio non era nemmeno dichiarato - una fonte oltre il budget
veniva presentata come «testo integrale non disponibile», che e' un'altra cosa.

`extract_plan_from_sources` fa una estrazione **per fonte**, a testo intero e in
parallelo, e fonde i piani parziali con la regola deterministica degli
emendamenti (`merge_process_understanding`): nessun LLM nel merge, identita'
stabile per le liste, ordine delle fonti stabile - quindi due ricostruzioni sulle
stesse fonti danno lo stesso piano.

Un dettaglio che sembra un dettaglio e non lo e': i percorsi ordinati
(`sequence`, `main_success_path`) si fondono in `append` e non in `replace`. Nel
merge di un emendamento chi dichiara un percorso lo sta riordinando; qui i due
piani sono **due letture parziali dello stesso processo**, e sostituire
lascerebbe nel piano i soli passaggi di chi ha parlato per ultimo.

Il giudizio di qualita' si da' una volta sola, sul piano fuso: chiederlo per
fonte moltiplicherebbe le chiamate per giudicare frammenti che nessuno usera' da
soli.

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

## Nessun successo senza rilettura

L'agente diceva "ho aggiornato la review sulla base delle evidenze" e la review a
schermo restava a zero attori; diceva "il canvas e' stato aggiornato e verificato"
avendo prodotto start ed end. Nessuna delle due era una bugia del modello: era il
runtime che dichiarava successo sulla base dell'**intenzione** di scrivere. Il
writer non sollevava eccezioni, quindi il turno si chiudeva bene.

`backend/workspace_services/write_verification.py` rende obbligatorio il terzo
passo — write → persistence → **read-after-write** → success:

- `verify_review_persisted` rilegge la review e rifiuta una versione che non e'
  salita o un piano senza attori, partecipanti ne' attivita';
- `verify_bpmn_model_persisted` rilegge il canvas e confronta gli elementi, non il
  testo del documento: due serializzazioni della stessa topologia differiscono per
  spazi, e confrontare stringhe farebbe fallire scritture riuscite.

Tre punti dove il falso successo passava, chiusi:

1. **il piano vuoto rendeva la validazione vuota.** `validate_canvas_against_process`
   degradava a *warning* cio' che non poteva confrontare, quindi uno start → end
   tecnicamente valido usciva senza issue — e senza issue il runtime dichiarava
   completato. Ora un piano con attivita' e un canvas che non ne rappresenta
   nessuna e' una *issue*; e se il piano manca del tutto mentre l'evidenza esiste,
   "nessuna issue" viene riconosciuto per quello che e': controllo non eseguito.
2. **la verifica leggeva lo stato del run.** Ora legge lo snapshot dell'autorita' e
   l'XML dal database: uno stato che si valida da solo verifica di aver avuto
   l'intenzione giusta.
3. **una costruzione che non scriveva niente non falliva.** Il canvas salvato
   identico a quello di partenza usciva come "ho preparato il lavoro sul canvas" —
   una frase che non dice ne' fatto ne' fallito. Ora e' `failed`, e il messaggio lo
   dice.

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

`tests/test_agentic_canvas_runtime_e2e.py` — parte dallo stato in cui il difetto
viveva davvero: tre interviste agli atti e **nessun piano**. Il file sotto partiva
da un processo con il piano gia' preparato, che e' lo stato giusto per verificare
che la conoscenza attraversi e quello sbagliato per accorgersi che non c'era.
Verifica che le tre voci arrivino con le loro parole, che il piano nasca dal
corpus e dichiari le fonti, che una quarta intervista lo renda da rifare e una
risposta del consulente no, che la soglia della bozza si apra dove quella della
validazione resta chiusa, e che nessun write venga dichiarato senza rilettura.

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

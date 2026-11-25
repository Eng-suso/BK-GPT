# Registro del VPT

Una voce per ogni sessione che chiude o tocca un blocco di [`PLAN.md`](./PLAN.md),
**la più recente in cima**. Chi inizia legge le ultime tre.

Modello:

```markdown
## AAAA-MM-GG — <blocco> — <fatto | in corso | bloccato>

- Branch / PR: ...
- Meta: ... → misura ottenuta: ... (comando: `...`)
- Iterazioni: 1) cosa provato → numero; 2) ...
- Cosa è cambiato: ...
- Decisioni (con chi le ha prese): ...
- Prossimo passo: ...
```

---

## 2026-11-25 — PROTO-01 protocollo sperimentale — fatto

- Branch / PR: `docs/vpt-protocol`, #190, CI verde.
- Meta: `docs/vpt/PROTOCOL.md` con categorie, NOT VALIDATED per log e metrica, nessun log
  escluso, holdout congelati per hash prima di G3b, divisione train / validazione / test,
  budget, go/no-go; più un test che fallisce se il codice di selezione legge un holdout →
  consegnata. Misura: `test_protocol.py` 124/124 (`--noconftest`), `tests/simulation` sullo
  stack reale 885 passati e 5 saltati con la guardia attiva, `protocol_properties.py` su
  25/25 log di sviluppo, 0 non disponibili.
- Holdout, scelti e congelati alle 08:12 UTC del 2026-11-25 (commit `476e705`) prima di ogni
  misura: Production, ConsultaDataMining 2016-18, PurchasingExample, confidential_2000
  (pacchetto Camargo 2022, CC BY 4.0), BPIC 2015 Municipality 1 e BPIC 2011 Hospital (4TU,
  aggiunti al manifest). Lucchetto `1cfaa147a37187c1a319968f200c99d1cc5918ac0795c8a95e8ee70286c35cdb`.
  Letti per sceglierli solo nomi, dimensioni, licenze e la presenza di `qbp:` nel BPMN
  confidential; `cvs_pharmacy` non è un holdout: stesse attività di Pharmacy.
- Iterazioni: 1) regola dei casi tagliati "fuori dal 95% delle attività finali" → 6% su
  AcademicCredentials e 5% su BPIC 2012 W, per costruzione; ora conta l'eccesso sui casi
  maturi di A (2,5% e 0,7%); 2) BPIC 2013 incidents ha arrivi di B ×204 rispetto ad A:
  aggiunta la regola degli arrivi (fuori da ×0,5-×2, CAR NOT VALIDATED), uguale per tutti.
- Identificabilità: 3 log del paper e 20 sintetici validano le metriche osservabili; BPIC 2012
  NOT VALIDATED su W1, NGD, RED e durate; BPIC 2013 su W1, NGD, RED, CAR e durate (AED, CED,
  risorse valide). Cause delle attese, parametri veri e controfattuale solo sui sintetici.
- Code review: `code-review` 9 rilievi, tutti corretti: file derivati dagli holdout nel
  pacchetto Camargo (log simulati da modelli addestrati sugli holdout, BPMN vero modificato)
  ora chiusi per cartella e per prefisso; fase per thread invece che globale; lucchetto LF in
  `.gitattributes` (impronta stabile su Windows); `O_ACCMODE` assente su Windows; collegamenti
  fisici chiusi per inode; `.json` e `.xml` tolti dalle estensioni bloccate (falsi allarmi su
  `production.json`); colonna in più nella tabella; nessun sintetico saltato in silenzio;
  HANDOFF aggiornato. `backend/CODE_QUALITY.md`: proprietà in una dataclass e verdetti e
  categorie `Literal` invece di `dict` e stringhe libere. ast-grep 4 regole: 0. ruff e mypy
  puliti. `simplify`: i 4 revisori si sono fermati per il limite d'uso; revisione fatta in
  sessione: una sola funzione SHA-256, log e percorsi del harness riusati, controllo
  dell'hook solo su stringhe. Non applicati: `cases()` calcolato più volte in `properties`
  (script da 20 s), import dei moduli che vogliono il database nel test (serve lo stack).
  Nessuna autenticazione o isolamento fra clienti: niente `security-review`.
- Skill: `code-review`, `simplify`, `docs` (lettura del Master Plan V2). Nessuna di
  frontend: punto di ricerca senza UI, niente gate UX.
- Branch aperti all'inizio: tutti indietro rispetto a `main` e già mergiati, tranne
  `docs/vpt-no-contact` (#188, decisione di Sohayb), mergiato su `main` durante la sessione
  e ripreso qui.
- Decisioni (Sohayb, 2026-11-25): confermate così le soglie del §4, il budget del §6 e il
  go/no-go del §7. Nessuna meta abbassata.
- Prossimo passo: G3b, dentro `selection_phase()`, con le schede del §7 scritte prima.

---

## 2026-11-25 — VAL-01 validazione formale all'import — fatto

- Branch / PR: `feat/sim-formal-validation`, #189.
- Meta (confermata da Sohayb il 2026-11-25, prima era *proposta*): all'import nessun
  deadlock né livelock, fine raggiungibile da ogni stato, uscita da ogni ciclo > 0 e
  ripetizioni attese finite; AcademicCredentials di G3 rifiutato; 19 scenari del dataset e
  scenari SIMOD validi di G3 passano; messaggio in linguaggio di business; gate UX →
  raggiunta. Misura: `tests/simulation/test_soundness.py` 51/51 (19/19, 8/8, `_diff` e
  `_fuzz` rifiutati; ciclo con uscita 0,25 → 4 esecuzioni attese); API 400
  `process_cannot_finish` su import e run; e2e `simulation-import-validation` 6/6
  (chromium, mobile-chrome, axe pulito) e gli altri e2e d'import 14/14; `tests/simulation`
  sullo stack 812 passati; vitest simulazione 454/454.
- Iterazioni: 1) gioco dei gettoni con un ordine fisso → meta sui dati raggiunta subito;
  2) messaggio ripetitivo → «cosa non torna» e «cosa fare» separati, nome della decisione;
  3) due test di import toglievano l'uscita di un ciclo: ora tengono l'uscita (il rifiuto
  è corretto); 4) code review: il verdetto dipendeva dai nomi degli elementi → passo
  massimo; bozze e what-if → verifica anche al run; 5) simplify.
- Gate UX (`docs/vpt/ux/val-01/`, desktop 1440 × 900 e Pixel 7, aperti e letti): prima il
  titolo «alcuni casi non arriverebbero mai alla fine», poi il motivo con i nomi delle
  attività, «Cosa fare» a capo, «lo scenario non è cambiato», id nel motivo tecnico chiuso.
  Corretto: «Cosa fare» annegato nel paragrafo; «il motore» → «la simulazione»;
  «scoperta dal log» → «ricalcola il modello dai dati storici»; «nei dati … dai dati».
- Code review: `code-review` 8 rilievi, 7 corretti (nomi, inclusive > 10 rami, blocchi
  persi al limite di stati, bozze e what-if, gergo, attese calcolate sempre, HANDOFF),
  1 motivato (testo solo in italiano, come IMP-01). `backend/CODE_QUALITY.md`: errore di
  dominio tipizzato, nessun `Any`. ast-grep 4 regole: 0; ruff pulito; mypy pulito sui file
  nuovi. `simplify` 4 revisori: 14 applicati, 4 saltati con motivo (parser BPMN comune,
  cache fra import e run, endpoint di sola verifica, codice delle attese tenuto come prova
  della meta). Nessuna autenticazione o isolamento toccati: niente `security-review`.
- Skill: `react-ui-patterns`, `ui-visual-validator`, `code-review`, `simplify`.
- Decisioni: meta confermata da Sohayb; la verifica vale anche al run (oltre l'import),
  perché bozze e what-if non passano dall'import.
- Prossimo passo: G3b dopo PROTO-01; B3.3 usa `require_sound` come criterio.

---

## 2026-11-25 — Prosimos per l'MVP, nessun contatto con i titolari — fatto

- Branch / PR: `docs/vpt-no-contact`, #188. Solo piano e documenti; Master Plan V2
  corretto nel Claude Docs.
- Decisione (Sohayb, dopo aver parlato con chi di dovere): Prosimos resta il motore per
  l'MVP e per i test del prodotto con le aziende; dopo l'MVP si sostituisce con un motore
  nativo sull'IR o con licenza permissiva (ENG-02, dietro ENG-01). Nessun contatto con i
  titolari del codice: la richiesta esce da LIC-01.
- Mete: nessuna abbassata.

---

## 2026-11-24 — Master Plan V2 diventa un programma di ricerca — fatto

- Branch / PR: `docs/vpt-research-program`. Solo piano e documenti; Master Plan V2
  aggiornato nel Claude Docs (otto suggerimenti accettati da Sohayb, più North Star,
  protocollo, Simulation Engine Interface e ordine di esecuzione).
- Fatti verificati:
  - DeliR ha una propria IR (`backend/simulation/ir/`) compilata per Prosimos, ma nessun
    motore di esecuzione proprio.
  - All'import oggi c'è solo l'allineamento fra IR e BPMN (`ir/bpmn_check.py`), nessuna
    validazione formale.
  - Prosimos 2.1.0 è su PyPI dal 2026-09-21, senza licenza nei metadati, ed è la versione
    del runner.
  - AT-KDE ha una versione estesa su Process Science 3:9 (2026),
    doi:10.1007/s44311-026-00041-z.
- Decisioni (Sohayb):
  1. SIMOD resta un benchmark.
  2. Obiettivo: un motore proprietario di discovery e simulazione, validato,
     utilizzabile commercialmente e indipendente. Valore originale su quattro livelli:
     Automatic Model Selection, Causal Simulation, Adaptive Calibration, Uncertainty
     Quantification.
  3. North Star su cinque dimensioni: predictive accuracy, formal correctness,
     counterfactual reliability, computational efficiency, technological independence.
  4. Prima LIC-01, PROTO-01, VAL-01, ENG-01 e G3b; nessun candidato implementato prima.
  5. Nessun log escluso: BPIC 2013 resta, con le metriche non identificabili dichiarate
     NOT VALIDATED. Holdout indipendenti, validazione controfattuale, benchmark
     computazionale.
  6. Ogni componente ha criteri quantitativi, test e go/no-go scritti prima.
- Mete: quelle dei punti nuovi sono *proposta*, da confermare. Nessuna meta esistente
  abbassata; B3 ora dipende da G3b e da B3.1-B3.3.
- Prossimo passo: LIC-01, PROTO-01, VAL-01, ENG-01 in sessioni parallele.

---

## 2026-11-24 — IMP-01 avviso sugli arrivi troncati — fatto

- Branch / PR: `feat/sim-import-expon-warning`, #185.
- Meta: importando uno scenario con arrivi `expon` e media vicina al massimo, DeliR
  avvisa in linguaggio di business con cosa cambia e cosa fare; lo scenario resta
  com'era; avvisano le 4 Procure_to_Pay, nessuno dei 15 altri; gate UX → raggiunta.
  Misura: `tests/simulation/test_prosimos_import.py` 118/118 (19 scenari: 4 avvisano,
  15 no; arrivi ricompilati identici al file), API 2 test sullo stack reale, e2e
  `simulation-import-arrivals` 4/4 (chromium e mobile-chrome, axe pulito, controllo
  anti-gergo), vitest simulazione 452/452, `tests/simulation` sullo stack 746 passati.
- Iterazioni: 1) regola sul codice di pix_framework 0.15 (rifiuto e ricampionamento,
  non taglio al massimo): media prodotta 1240,5 s contro 1241,8 campionati, +45%;
  2) nota `warning` e pannello d'import; 3) prova col file vero: il consulente veniva
  fermato da 3 ID di porte di unione da associare → il template li elenca; 4) gate UX:
  su mobile il bottone schiacciava il testo in colonna e la media appariva
  "30.083333333333332" → bottone sotto il testo, media a 3 cifre; 5) code review e
  simplify.
- Gate UX (`docs/vpt/ux/imp-01/`, desktop 1440 × 900 e Pixel 7, aperti e letti):
  risposta e azione prima dei dettagli, nessun "esponenziale", "Prosimos", "node-…"
  nel percorso ordinario, nessun testo tagliato dopo la correzione. "Prima" non
  catturato: il flusso col file vero si fermava alla richiesta di associare gli ID.
- Code review: `code-review` 8 rilievi, tutti corretti (avviso falso con ritmi per mese,
  arrotondamento che azzerava i passi brevi, `withArrival` che perdeva i mesi, toast
  senza avviso con limiti non validi, arrotondamento diverso Python/JS, unità scelte
  prima di arrotondare, rimando in inglese a dettagli in italiano, HANDOFF). `simplify`
  (4 revisori): porte di unione dal template del server invece di un parser BPMN nel
  client, campi di mappatura calcolati una volta, secondi nell'avviso, golden
  condiviso Python/TS, stesso controllo della lingua delle altre viste. Non applicati:
  `arrivalsRunFaster` privato (lo usano i test e il golden), `_arrival_notes` che
  restituisce una lista (stile delle altre note), calcolo pigro delle porte (sparito
  col template). `backend/CODE_QUALITY.md`: tolto un `Any`; regola duplicata
  frontend/backend motivata (l'editor valida le bozze senza chiamare il server) e
  tenuta uguale dal golden. ast-grep 4 regole: 0 rilievi; ruff e mypy puliti. Nessuna
  modifica ad autenticazione o isolamento: niente `security-review`.
- Skill: `ui-visual-validator`, `code-review`, `simplify`.
- Decisioni: soglia 10% fra media scritta e prodotta; correzione proposta "massimo ≥ 5
  volte la media" (scarto 3%).
- Prossimo passo: B3 (SIM-36b è chiuso).

---

## 2026-11-24 — SIM-36b baseline "B = A" sui log train/test — fatto

- Branch / PR: `feat/sim-benchmark-train-test`.
- Meta: "B = A" (impara dal train, prevede il test) misurata sui 3 log reali del paper con
  metriche, repliche e formato di B2, salvata con il comando per rifarla; BPIC 2013
  incidents marcato come non adatto al confronto A→B → raggiunta. Comando:
  `run_baseline.py AcademicCredentials BPIC_2012_W BPIC_2017_W` (seed 20261124, 10 repliche, ore):

  | Log | W1 | NGD | RED | AED | CED | CAR |
  | --- | --- | --- | --- | --- | --- | --- |
  | AcademicCredentials | 28,827 ± 3,601 | 0,179 ± 0,006 | 25,856 ± 2,223 | 62,309 ± 6,194 | 1,391 ± 0,116 | 95,460 ± 17,106 |
  | BPIC_2012_W | 28,061 ± 2,000 | 0,083 ± 0,005 | 10,140 ± 2,565 | 29,710 ± 4,414 | 0,800 ± 0,155 | 38,215 ± 4,309 |
  | BPIC_2017_W | 30,602 ± 1,481 | 0,079 ± 0,001 | 11,359 ± 1,570 | 42,785 ± 4,042 | 0,660 ± 0,011 | 35,916 ± 3,821 |

  Contro lo scenario SIMOD del paper di B2: "B = A" migliore in 17 confronti su 18, pari
  su CAR di AcademicCredentials. Stessi file bit per bit su due passate; i JSON SIM-36 di
  BPIC 2012 e 2013 rilanciati con metriche identiche (aggiunti solo `split` e la marcatura).
- Iterazioni: 1) estensione di `run_baseline.py` (A = train, B = test, fuso UTC perché i
  CSV non ne hanno) → numeri uguali a quelli della decisione del 2026-11-24; 2) la
  marcatura di BPIC 2013 non compariva con il JSON vecchio: rilancio dei BPIC.
- Code review: `code-review` 7 rilievi, tutti corretti (log mancante in B2 → nota invece
  di KeyError; file di B2 scelto dal chiamante, `--b2`; un log con seed diverso non
  cancella il confronto degli altri; nota di BPIC 2013 solo se il log è nella cartella;
  `compare_with_paper` usa la regola comune; docstring; etichette pubbliche
  `METRIC_LABELS`). `backend/CODE_QUALITY.md`: nessun rilievo (script di benchmark, nessun
  errore inghiottito: log indisponibile o confronto non fatto sono scritti). ast-grep
  (4 regole): 0. ruff e mypy puliti. `simplify` con 4 revisori: una fonte per log
  (`SOURCES`) invece dei rami `if key in REAL_LIFE`, `ROOT` e `manifest_entry(id)`
  riusati, un solo `cell()` per media ± intervallo, etichetta del benchmark nella fonte.
  Non applicati, con motivo: `within_intervals` resta identica a G3 (stesso hunk, merge
  pulito); costanti dei percorsi train/test comuni con G3 (da fare quando G3 è su main);
  rilettura dei CSV nei test (≈20 KB, trascurabile).
- Skill: `code-review`, `simplify`. Nessuna di frontend: punto di ricerca senza UI,
  niente gate UX.
- Decisioni: nessuna meta cambiata.
- Prossimo passo: G3 e B3 misurano il twin contro questa baseline; G3 può usare
  `run_baseline.measure` invece della sua copia del gemello.

---

## 2026-11-24 — G3 spike SIMOD — fatto

- Branch / PR: `spike/sim-simod-discovery`.
- Meta: SIMOD scopre i 3 log reali dal train, lo scenario si importa in DeliR (FUZZY
  compresi), si valuta sul test con l'harness di B2 contro lo scenario del paper, decisione
  scritta → raggiunta. Comandi: `tests/simulation/benchmark/g3/discover.sh all`, poi
  `uv run python tests/simulation/benchmark/g3/evaluate.py` sullo stack reale (seed
  20261124, 10 repliche). Tabelle complete in `tests/simulation/benchmark/g3/results.md`.
- Misura (ore, media ± IC 95%, più basso è meglio; "ingenuo" è il "B = A" di SIM-36 con
  A = train e B = test):

  | Log | Scenario | RED | AED | W1 cycle time | CAR |
  | --- | --- | --- | --- | --- | --- |
  | AcademicCredentials | SIMOD 5.2.1 fissi | 6649 ± 2136 | 6904 ± 2196 | 295,4 ± 29,7 | 254,2 ± 36,4 |
  | AcademicCredentials | SIMOD 5.2.1 FUZZY | 10074 ± 3042 | 10372 ± 3061 | 324,0 ± 67,2 | 270,1 ± 41,5 |
  | AcademicCredentials | paper in DeliR | 77,5 ± 0,2 | 121,4 ± 23,3 | 174,8 ± 0,4 | 131,0 ± 25,9 |
  | AcademicCredentials | ingenuo | 25,9 ± 2,2 | 62,3 ± 6,2 | 28,8 ± 3,6 | 95,5 ± 17,1 |
  | BPIC 2012 W | SIMOD 5.2.1 fissi | 178,0 ± 0,1 | 172,6 ± 9,2 | 175,3 ± 0,0 | 41,5 ± 6,5 |
  | BPIC 2012 W | SIMOD 5.2.1 FUZZY | 87,5 ± 9,8 | 123,0 ± 9,6 | 307,4 ± 50,1 | 66,0 ± 9,1 |
  | BPIC 2012 W | SIMOD 5.2.1 fissi + ritardi estranei | 65,3 ± 2,4 | 92,7 ± 10,9 | 42,5 ± 2,1 | 65,8 ± 10,4 |
  | BPIC 2012 W | paper in DeliR | 178,5 ± 0,0 | 221,5 ± 8,2 | 175,7 ± 0,0 | 85,8 ± 8,1 |
  | BPIC 2012 W | ingenuo | 10,1 ± 2,6 | 29,7 ± 4,4 | 28,1 ± 2,0 | 38,2 ± 4,3 |
  | BPIC 2017 W | SIMOD 5.2.1 fissi | 183,0 ± 0,0 | 244,4 ± 14,2 | 252,9 ± 0,0 | 112,7 ± 11,6 |
  | BPIC 2017 W | SIMOD 5.2.1 FUZZY | 167,1 ± 0,7 | 241,8 ± 12,0 | 230,2 ± 0,9 | 123,6 ± 11,3 |
  | BPIC 2017 W | SIMOD 5.2.1 fissi + ritardi estranei | 8,1 ± 0,5 | 106,3 ± 9,3 | 17,9 ± 1,7 | 154,6 ± 9,0 |
  | BPIC 2017 W | paper in DeliR | 183,5 ± 0,0 | 303,4 ± 9,7 | 253,3 ± 0,0 | 169,6 ± 9,4 |
  | BPIC 2017 W | ingenuo | 11,4 ± 1,6 | 42,8 ± 4,0 | 30,6 ± 1,5 | 35,9 ± 3,8 |

  - Contro lo scenario del paper: SIMOD 5.2.1 a calendari fissi è migliore su 4/4 metriche
    sia su BPIC 2012 W sia su BPIC 2017 W. Su AcademicCredentials è molto peggiore.
  - Contro l'ingenuo: vince solo BPIC 2017 W con i ritardi estranei, su RED (8,1 contro 11,4)
    e W1 (17,9 contro 30,6). AED e CAR restano dell'ingenuo ovunque; BPIC 2012 W CRISP è pari
    su CAR. In tutto 2 coppie log × metrica vinte su 12.
- Tempo di discovery (SIMOD, preprocessing + pipeline, 4 vCPU; wall-clock nel report):
  AcademicCredentials 106 s, BPIC 2012 W 687 s, BPIC 2017 W 1545 s a calendari fissi; FUZZY
  e ritardi estranei riusano quel BPMN e aggiungono 389-1133 s. I `diff` sono stati misurati
  con 3 discovery in parallelo.
- Cosa l'import ha dovuto adattare: niente. Solo note informative: attività istantanee
  (1-16 per scenario) e "calendari probabilistici" sui FUZZY (306 calendari su
  AcademicCredentials, importati grazie a CAL-01). I timer dei ritardi estranei entrano
  senza note. DeliR riproduce la valutazione di SIMOD stesso (BPIC 2012 W fissi: RED
  178,0/178,0, W1 175,3/175,3; tabella in `results.md`): l'import è fedele, gli scarti
  sono del modello scoperto.
- Cosa SIMOD non sa fare (visto qui):
  - **Cicli senza uscita.** Su AcademicCredentials il gateway dopo "Avanzar recepcion
    documentos" ha uscita 0 e ritorno 1 (attività in 2 casi su 398 del train): chi entra
    ripete ~1000 volte, RED 6649 h. SIMOD lo vede nella sua valutazione (RED ~6240 h) e lo
    sceglie lo stesso: la sua metrica di ottimizzazione (2-gram) non lo punisce. Riaperto il
    ciclo alla frequenza del train (`fix_dead_loops.py`, diagnosi, non uno scenario SIMOD):
    RED 77,9 ± 0,5, pari al paper; AED 233 e CAR 254 restano peggiori.
  - **Ritardi estranei su AcademicCredentials:** SIMOD crolla (timestamp nel 2262,
    `OutOfBoundsDatetime` in pandas) per lo stesso ciclo. Traccia in `g3/failures/`.
  - **Riproducibilità:** nessun seed (hyperopt): rilanciata, la discovery dà scenari
    diversi. Gli scenari usati sono nel repo.
  - **Arrivi:** CAR peggiore dell'ingenuo in 7 scenari SIMOD su 8, pari nell'ottavo (BPIC 2012 W fissi).
  - I calendari FUZZY non sono meglio dei fissi: W1 peggiore su BPIC 2012 W (307 contro 175).
- Nota di B2 su Procure_to_Pay: non tocca questi confronti. Gli arrivi scoperti sono tutti
  lognorm (lo scenario del paper usa gamma), con media lontana dal massimo; nessun `expon`
  troncato.
- **Decisione G3: SIMOD sì, come motore di discovery di DeliR, a queste condizioni.**
  1. Gira come lavoro in background in un servizio a parte, come il runner: Python 3.12,
     Java, da 2 a 45 minuti per log su 4 vCPU. Lo scenario prodotto si salva con versione e
     configurazione, perché la discovery non è riproducibile.
  2. Variante di partenza: calendari fissi + ritardi estranei. È l'unica che si avvicina
     all'ingenuo (BPIC 2017 W lo batte su RED e W1); senza ritardi W1 è 6-8 volte quello
     dell'ingenuo.
  3. Prima di proporlo al consulente, DeliR controlla lo scenario: un gateway che torna
     indietro con probabilità 1 e uscita 0 blocca l'import con un messaggio chiaro (oggi
     passa in silenzio). Su log piccoli come AcademicCredentials (398 casi) lo scenario non
     è affidabile.
  4. Uno scenario SIMOD non è "validato" finché non batte "B = A" sul test con gli
     intervalli: oggi succede su 2 coppie log × metrica su 12. La meta H1 di B3 (batte "B =
     A" su ≥ 3 log) SIMOD da solo non la raggiunge: B3 parte da SIMOD con i ritardi
     estranei come base e lavora su arrivi (CAR) e attese (AED).
- Cosa è cambiato:
  - `tests/simulation/benchmark/g3/`: configurazioni, `discover.sh`, `evaluate.py`,
    `fix_dead_loops.py`, scenari scoperti, risultati, README con i comandi.
  - `eval_harness.py`: `Scenario.source` per scenari esterni; `import_into_new_process` e
    `within_intervals` condivisi. Verificato che `b2/baseline.json` dei 3 reali resta
    identico.
  - Nessun file di prodotto toccato; `run_baseline.py` e B6 non toccati, solo riusato
    `NaiveTwin`.
- Iterazioni:
  1) Gemello ingenuo mio, spostato sul primo inizio, sostituito da quello di SIM-36 (mediana,
     repliche con intervallo): AED di AcademicCredentials da 165 a 62 h.
  2) Aggiunta la variante con i ritardi estranei (configurazioni `_extr` di SIMOD) quando è
     stato chiaro che il divario con l'ingenuo è nelle attese, tema del paper.
  3) Le prime discovery hanno perso `runtimes.json` per una modifica allo script in corsa:
     copiato a mano, script ora tutto dentro `main`.
- Code review:
  - `code-review`: 10 rilievi, tutti corretti. I principali: `all` si fermava al crash noto;
    una discovery fallita lasciava lo scenario vecchio; il controllo del seed di B2 arrivava
    dopo 15 minuti di simulazioni; doppio import per scenario; tempi ereditati sulle diagnosi.
  - `backend/CODE_QUALITY.md` e le 4 regole ast-grep: 0 rilievi; aggiunti i test delle
    trasformazioni deterministiche (`g3/test_g3_spike.py`).
  - `simplify` con 4 revisori: 5 corretti (regola degli intervalli condivisa con B2,
    grafo BPMN del backend nella diagnosi, etichette uniche, cartella nel risultato, niente
    `deepcopy`) e 3 saltati con motivo (letture ripetute dei log < 1% del tempo; percorsi dei
    log scritti a mano, pochi e a basso rischio in uno spike).
  - Nessuna autenticazione o isolamento fra clienti toccati: niente `security-review`.
- Skill: `code-review`, `simplify`. Nessuna di frontend: punto di ricerca senza UI, quindi
  niente gate UX.
- Con la meta di B3 decisa da Sohayb lo stesso giorno (batte "B = A" train/test su W1, RED e
  AED senza sovrapposizione), nessuno scenario SIMOD passa: il migliore (BPIC 2017 W con
  ritardi estranei) vince su RED e W1, perde su AED.
- Prossimo passo: SIM-36b (il "B = A" train/test è già misurato qui, da portare nel
  benchmark) e IMP-01, poi B3 con SIMOD (fissi + ritardi estranei) come candidato di
  partenza; proposto un punto Prod per il controllo dei cicli senza uscita nell'import.

---

## 2026-11-24 — B6 throughput del simulatore (G2) — fatto

- Branch / PR: `spike/sim-throughput`.
- Meta: run al minuto misurati sul percorso del prodotto (API, coda, worker, runner
  Prosimos 2.1); what-if 10 ripetizioni × 1.000 casi in meno di 60 s dalla richiesta al
  risultato salvato e leggibile → raggiunta. Misura finale (comando:
  `uv run python tests/simulation/benchmark/throughput.py --check`, 4 CPU, 3 giri):

  | Worker del runner | What-if (s) | Run/min |
  | --- | --- | --- |
  | 1 | 22,9-26,1 | 23-26 |
  | 2 | 14,3-14,5 | 41-42 |
  | 4 | 11,3-11,5 | 52-53 |

- Iterazioni: 1) script di carico e riga delle fasi nel worker; prima misura sul codice
  di `main`: 21,5-23,6 / 14,9-18,8 / 11,5-16,3 s, meta gia' raggiunta; impronte salvate;
  2) profilo: motore = Prosimos, analisi 0,2 s, salvataggio 0,1 s, export del log 0,3 s
  a run; con piu' worker i posti oltre il primo aspettavano il giro periodico (10 s);
  3) la richiesta di un gruppo avviava piu' drenaggi → 10,1-11,1 s con 4 worker;
  4) `simplify` ha portato la correzione alla radice: la richiesta sveglia il giro
  della coda; 5) l'harness B2 ha mostrato una corsa reale (run "completed" prima del
  suo log, 404): completamento atomico con KPI e log; 6) misura finale e harness B2.
- Risultati invariati: impronte di KPI e log identiche in ogni giro e al riferimento
  (`b6/fingerprints.json`); harness B2 rilanciato: `baseline.json` identico bit per bit
  (`24809a7f…`), 9/9 dentro. Suite `tests/simulation` sullo stack: 703 passati.
- Code review: `code-review` 8 rilievi, tutti corretti (drenaggi falliti non attesi,
  attesa in coda di un run rimesso in coda, regex delle fasi, riga anche per i run
  falliti, run rieseguito, orologi diversi, commenti, file di log non chiusi);
  `backend/CODE_QUALITY.md`: un parser di orari duplicato, rimosso (si usa quello della
  coda); 4 regole ast-grep: 0 rilievi; ruff e mypy puliti. `simplify` con 4 revisori:
  corretti il pool di drenaggi nella richiesta (sostituito dal risveglio del giro), il
  riuso di `ProductPath` e del seed di B2, i nomi delle fasi in un posto solo, polling
  a 0,5 s, campo `sum` inutile. Non applicati, con motivo: timer passato come argomento
  invece di una contextvar (stato nascosto peggiore), colonna `queued_at` per i run
  rimessi in coda (migrazione per un caso raro), ritocchi di forma dello script
  (intestazioni, URL, ExitStack). Nessuna modifica ad autenticazione o isolamento:
  niente `security-review`.
- Skill: `code-review`, `simplify` (nessuna di frontend: lavoro di backend). Nessun
  gate UX: il punto non cambia cio' che il cliente vede.
- Decisioni: scenario fisso Loan_Application tradotto nei campi del pannello, perche'
  le ripetizioni esistono solo su `simulation-runs`.
- Prossimo passo: B7 (ottimizzazione) puo' partire quando V3 e' chiuso; G3 e B3 come
  da piano.

---

## 2026-11-24 — decisioni di Sohayb su benchmark, B3, import e infrastruttura — fatto

- Branch / PR: `docs/vpt-decisions-2026-11-24`. Solo piano e documenti.
- Misure che hanno portato alle decisioni (strumenti di SIM-36, seed 20261124):
  - **Taglio A/B su BPIC 2012.** Metà dei casi, metà del tempo e metà del tempo senza
    l'1% di code danno W1 16,3, 16,5 e 17,6 h. Il criterio conta poco.
  - **Taglio A/B su BPIC 2013 incidents.** Con ogni taglio il 100% dei casi di B è
    troncato dalla fine del log; con la metà del tempo A ha 7 casi. Il log è una foto
    degli incidenti aperti a maggio 2012, non un flusso.
  - **"B = A" sui 3 log train/test del paper** contro il modello SIMOD simulato da B2:
    "B = A" vince 14 confronti su 15 con intervalli separati (pari su CAR di
    AcademicCredentials). W1 vale 28,8 contro 174,8 h, 28,1 contro 175,7 h e 30,6
    contro 253,3 h.
- Decisioni (Sohayb, 2026-11-24):
  1. Il benchmark A→B principale sono i 3 log train/test; nuovo punto SIM-36b. BPIC
     2012 resta. BPIC 2013 incidents si marca come non adatto al confronto A→B.
  2. La meta di B3 sui sintetici è confermata (gateway ±0,05, durate ±10%). Sui reali
     "batte B = A" diventa: sui 3 log train/test, su W1, RED e AED, con intervalli al
     95% separati. NGD resta fuori dal criterio perché "B = A" ripete tracce reali e
     parte avvantaggiato sui percorsi.
  3. L'import avvisa sugli arrivi `expon` con media vicina al massimo; nuovo punto IMP-01.
  4. `DELIR_ADMIN_TOKEN` in staging e prod e la VM per l'isolamento fra clienti li
     sblocca Sohayb.
- Mete abbassate: nessuna. La meta di B3 sui reali è più precisa e più dura (tutti e 3
  i log, tre metriche).
- Prossimo passo: SIM-36b in una sessione nuova, poi G3 e B3; IMP-01 in parallelo.

---

## 2026-11-24 — SIM-36 baseline pubblica "B = A" — fatto

- Branch / PR: `feat/sim-benchmark-baseline`, #178.
- Meta: baseline "B = A" misurata su BPIC 2012 e BPIC 2013 incidents e salvata nel repo con
  il comando per rifarla → raggiunta. Comandi: `run_baseline.py bpic2012`,
  `run_baseline.py bpic2013_incidents`; log scaricati con `fetch_datasets.py`, MD5 del
  manifest verificato. Seed 20261124, 10 repliche, ore:
  - BPIC 2012: W1 16,931 ± 1,518, NGD 0,055 ± 0,002, RED 16,554 ± 1,567, AED 60,281 ± 3,275,
    CED 0,222 ± 0,013, CAR 48,697 ± 2,653.
  - BPIC 2013 incidents: W1 383,995 ± 7,811, NGD 0,329 ± 0,004, RED 176,788 ± 3,981,
    AED 334,396 ± 16,091, CED 1,751 ± 0,079, CAR 290,944 ± 6,383.
  Stesso seed, stessi file bit per bit.
- Iterazioni:
  1) BPIC 2013 letto con 0 eventi: il ciclo di vita è un sottostato. Ora è parte
     dell'attività, con eventi istantanei.
  2) Spostamento di A non a settimane intere: CED 6,7 h su BPIC 2012, misurava la rotazione
     del calendario. Con le settimane intere: 0,35.
  3) Code review: l'ancoraggio sul minimo portava un caso del 2010 a spostare tutto, con
     AED 17.945 h. Con l'ancoraggio sulla mediana: 334 h.
  4) Ora legale: spostare in UTC perdeva un'ora (CED 0,21 dopo). Spostare ogni evento
     sull'orologio locale cambiava le durate a cavallo del cambio d'ora: ora si sposta
     l'inizio del caso.
  5) Il primo JSON perdeva la descrizione delle distanze, sovrascritta dalle metriche.
- Cosa è cambiato:
  - `run_baseline.py` usa le distanze di B2, scrive un file per log e non sovrascrive una
    misura con un motivo di indisponibilità.
  - `benchmark_datasets.py` scarica dal manifest, con una mappatura e un fuso per log.
  - `benchmark_metrics.py` è stato tolto.
  - `docs/simulation-benchmark.md` riscritto.
- Decisioni:
  - Ancoraggio sulla mediana e settimane intere: scelta di metodo, documentata.
  - Lo scarto fino a 3,5 giorni resta in AED e CAR.
  - Nessuna meta cambiata.
- Code review:
  - `code-review`: 9 rilievi, 7 corretti e 2 motivati.
  - `backend/CODE_QUALITY.md` e ast-grep: 0 rilievi.
  - `simplify` con 4 revisori: 5 corretti, 6 saltati con motivo (dettaglio nella PR).
- Skill: `code-review`, `simplify`. Nessuna skill di frontend: punto di ricerca senza UI,
  quindi niente gate UX.
- Prossimo passo: G3 e B3 misurano il twin contro questa baseline con lo stesso comando.

---

## 2026-11-24 — B2 harness di valutazione — fatto

- Branch / PR: `feat/sim-eval-harness`.
- Meta: (1) stesso seed, stesso `baseline.json` bit per bit sui 19 scenari →
  raggiunta: due passate complete con il seed 20261124, SHA-256 identico
  (`24809a7f…`), e `test_same_seed_same_baseline_bit_for_bit` sullo stack reale.
  (2) 3 log reali contro la riga `original` del paper, 10 repliche come il paper →
  9/9 dentro (comando: `uv run python tests/simulation/benchmark/eval_harness.py`):

  | Log | Metrica | DeliR | Paper | Scarto | Somma IC |
  | --- | --- | --- | --- | --- | --- |
  | AcademicCredentials | RED | 77,464 ± 0,210 | 77,211 ± 0,350 | 0,254 | 0,561 |
  | AcademicCredentials | AED | 121,397 ± 23,249 | 132,824 ± 26,746 | 11,427 | 49,995 |
  | AcademicCredentials | W1 cycle time | 174,837 ± 0,421 | 174,662 ± 0,962 | 0,175 | 1,383 |
  | BPIC 2012 W | RED | 178,538 ± 0,020 | 178,545 ± 0,013 | 0,007 | 0,034 |
  | BPIC 2012 W | AED | 221,446 ± 8,148 | 223,843 ± 8,438 | 2,397 | 16,586 |
  | BPIC 2012 W | W1 cycle time | 175,710 ± 0,036 | 175,721 ± 0,033 | 0,011 | 0,069 |
  | BPIC 2017 W | RED | 183,545 ± 0,019 | 183,555 ± 0,018 | 0,010 | 0,037 |
  | BPIC 2017 W | AED | 303,353 ± 9,738 | 296,035 ± 9,531 | 7,318 | 19,269 |
  | BPIC 2017 W | W1 cycle time | 253,314 ± 0,033 | 253,330 ± 0,021 | 0,017 | 0,053 |

  (3) baseline dei 16 sintetici con W1, NGD, RED, AED, CED, CAR e intervalli →
  `tests/simulation/benchmark/b2/baseline.md`.
- Iterazioni: 1) punti aperti: 10 repliche (script del paper, upstream `26c88a0^`),
  libreria Apache 2.0; la libreria 2.2 riproduce `metrics.csv` del paper a tutte le
  cifre dai suoi log; 2) formule portate in `log_distance.py`, test rosso poi verde
  contro i numeri della libreria (rel. 1e-9) e contro la riga del paper; 3) harness
  sul percorso del prodotto: 9/9 dentro al primo giro, nessuna metrica da correggere;
  4) code review e simplify (sotto); 5) misura finale due volte.
- Prova sui sintetici: Procure_to_Pay scarta ~250 h sugli arrivi perché il suo log di
  riferimento ha intervalli quasi costanti (mediana 1802 s, metà centrale 1789-1822 s)
  mentre Prosimos 2.1 legge `expon [1805, 5, 3600]` come esponenziale tagliato:
  semantica del motore che ha generato il log, non della pipeline (lo stesso JSON arriva
  al runner). Dettagli in `HANDOFF.md`, sezione B2.
- Code review: `code-review` 4 rilievi, tutti corretti (baseline parziale sovrascritta,
  `--replicas` non validato, KPI non confrontato con il log riletto, versione del motore
  mancante); `backend/CODE_QUALITY.md` e le 4 regole ast-grep: nessun rilievo;
  `simplify` 9 corretti, 6 saltati con motivo nella PR. Nessun codice di backend
  toccato, quindi niente `security-review`.
- Skill: `code-review`, `simplify` (nessuna di frontend: lavoro di ricerca e backend).
- Decisioni: metriche portate nel nostro codice invece del venv 3.12; W1 del cycle time
  del paper ricavato dai suoi log con la stessa libreria, bin di un'ora come SIMOD.
- Prossimo passo: SIM-36 e G3 in parallelo (ordine del piano), poi B3.

---

## 2026-11-24 — CAL-01 calendari probabilistici (FUZZY) di SIMOD — fatto

- Branch / PR: `feat/sim-fuzzy-calendars`. Il lavoro c'era già su quel branch (15
  commit di una sessione precedente, mai in PR, partiti prima di #170): ripreso,
  mergiato `origin/main`, verificato e completato.
- Meta: uno scenario SIMOD con calendari FUZZY si importa senza perdere la
  disponibilità probabilistica, si ricompila identico e gira sul runner Prosimos 2.1
  dello stack; nessun rifiuto per FUZZY → raggiunta. Misura sullo stack reale:
  scenario scoperto da SIMOD 5.2.1 (`differentiated_fuzzy`, fasce di 60 minuti) sul log
  `Insurance_Claims_train.csv` in `datasets/simod/discovered/Insurance_Claims_fuzzy/`;
  import e round trip 81/81 (`uv run pytest --noconftest tests/simulation/test_prosimos_import.py`),
  motore 32/32 (venv del runner), API 6/6 con
  `DELIR_TEST_PROSIMOS_URL=$PROSIMOS_BASE_URL`: import → coda → runner HTTP 2.1 →
  database, 100 casi, `completed`. Suite `tests/simulation` con Postgres: 681 passati.
  Disponibilità al 20% contro 95%: tempo di ciclo medio ~193.000 s contro ~1.800 s.
- Iterazioni (sessione precedente): granularità in minuti interi; disponibilità *o*
  carico in `is_available`; SIMOD installato e lanciato sul dataset; nota per il
  consulente; code review con 7 rilievi chiusi.
- Iterazioni (questa sessione): 1) mancava il run sul runner HTTP dello stack (il test
  API usava un motore finto): test nuovo sul percorso del prodotto; 2) leggendo
  Prosimos e pix_framework: SIMOD scrive la fascia fino a mezzanotte con `endTime`
  "00:00:00" e l'IR la rifiutava, cioè un rifiuto per FUZZY su scenari veri (quello del
  dataset finisce alle 15 e non lo mostrava); il motore leggeva "23:59:59" perdendo
  l'ultima fascia e spostava in silenzio gli orari fuori granulo. Test rossi, poi
  corretti; due casi sintetici del round trip usavano un granulo che non cadeva sui
  loro orari; 3) probabilità accettate e ignorate su fasce degli arrivi e delle durate:
  ora il tipo le esclude.
- Code review: `code-review` (3 rilievi, tutti corretti), `backend/CODE_QUALITY.md`,
  ast-grep (0 rilievi su `backend/simulation/ir`), ruff e mypy puliti; `simplify` con 4
  revisori: corretti posizione di `probability`, riuso di `_clock`, `MIDNIGHT`, un
  ciclo solo, loader condiviso dello scenario SIMOD. Non applicati, con motivo:
  `availability` resta un `Literal` esplicito accanto a `granule_minutes`
  (CODE_QUALITY: Literal per i modi); i controlli dell'import restano perché danno il
  percorso nel file; gli helper che rendono FUZZY gli scenari sintetici producono
  probabilità diverse di proposito. Efficienza: nessun rilievo (1,5 ms per
  validazione su 896 fasce).
- Skill: `code-review`, `simplify`, `ui-visual-validator`. Gate UX: screenshot desktop
  e mobile (pannello, pagina, focus da tastiera) in `docs/vpt/ux/cal-01/`, letti: la
  nota parla di persone e fasce, il dettaglio tecnico è dietro "Dettagli", nessun
  testo tagliato, focus visibile; e2e `simulation-prosimos-import` 10/10 su chromium e
  mobile-chrome.
- Prossimo passo: B2 (in corso in un'altra sessione); UX-01 è chiuso.

---

## 2026-11-24 — UX-01 reale contro simulato leggibile — fatto

- Branch / PR: `fix/ux-real-vs-simulated`, #173.
- Meta: nel percorso ordinario nessun termine tecnico, plurali corretti, pannello leggibile su
  mobile senza scorrere oltre il canvas, gate UX → raggiunta. Misura: e2e
  `e2e/simulation-eventlog.spec.ts` 14/14 su chromium e mobile-chrome con axe pulito e un
  controllo che fallisce se il testo visibile contiene IC 95%, P50, P90, 2-grammi, warm-up,
  errore assoluto medio, replica/repliche o KPI; vitest `src/features/process/simulation` 438/438.
- Skill: ui-ux-designer, web-design-guidelines, accessibility-compliance-accessibility-audit,
  ui-visual-validator; code-review, simplify.
- Prova del consulente (cosa ho cambiato e perché, rileggendo da non statistico):
  - "Validazione aggregata" → "Confronto con il log reale": dice cosa si confronta, non il metodo.
  - "1 repliche confrontate con 3 casi reali" → "1 simulazione a confronto con 3 casi reali.":
    "replica" e "run" sono gergo; il plurale era sbagliato. Ora i conteggi hanno _one/_other in it ed en.
  - Colonne "Media repliche · IC 95%", "Scarto medio", "Errore assoluto medio" → "Simulato (media)"
    e "Differenza"; IC, scarto ed errore assoluto vanno nei "Dettagli per specialisti" con
    distanze (2-grammi), percentili su tutti i casi, seed e warm-up.
  - P50/P90 → "Metà dei casi si chiude entro", "9 casi su 10 si chiudono entro": è la domanda
    che il consulente si fa. "Tempo di attraversamento" → "Durata di un caso".
    "Lavorazione" → "Tempo di lavoro". "KPI" → "Indicatore".
  - Verdetto spostato in alto ("prima la risposta") e riscritto in percentuali con soglie in parole.
  - Con una sola simulazione la tabella aggregata ripeteva quella della simulazione scelta: tolta.
    Con un gruppo resta, con gli stessi nomi di riga e la frase che spiega sopra/sotto.
  - L'avviso sui casi diversi ora dice i numeri ("Il log ha 3 casi, la simulazione 300 casi") e non
    nomina il warm-up; la nota sulla taratura è riscritta senza "capacità predittiva".
  - "abilitazione"/"eseguibile" → "quando il caso è pronto a partire"; i motivi in colonna sono più corti.
  - Avvisi a fondo pagina con plurali veri: "1 attività del log non è nel modello: resta fuori dal confronto".
- Mobile: sotto i 1199px il pannello dell'event log viene prima del disegno, e
  `overflow-anchor: none` evita che la pagina salti sul disegno quando un passo cambia altezza
  (prima il contenitore finiva scrollato a 721 px, sul canvas).
- Gate UX: 16 screenshot in `docs/vpt/ux/ux-01/` (desktop 1440×900 e Pixel 7; schermata e pannello
  intero; una simulazione, gruppo, dettagli aperti, log con soli completamenti), tutti aperti e
  letti. Correzioni nate dalla lettura: nomi diversi per lo stesso indicatore nelle due tabelle,
  marcatore del `<details>` sparito, motivo "non confrontabile" su 5 righe.
- Review: `code-review` 4 rilievi, tutti corretti; `simplify` 4 revisori, corretti 9 rilievi,
  saltati 2 fuori scopo (vedi PR e HANDOFF).
- Prossimo passo: B2 e CAL-01 proseguono nelle loro sessioni.

---

## 2026-11-24 — chiusura B1, stack reale, meta di B2 — fatto

- Branch / PR: #170 (B1a + B1b, chiude anche #169) mergiata; #171
  `env/vpt-local-stack`.
- Meta: #170 su `main` con CI verde → raggiunta. Stack reale avviabile in una sessione
  cloud senza Docker → raggiunta: `scripts/vpt_stack.sh start` in 9 s dopo il primo
  avvio; con lo stack `tests/server/test_app.py` 12/12 sul database vero e
  `test_simulation_ir_engine.py` 29/29 su Prosimos 2.1.
- Iterazioni: 1) #170 in conflitto con `main` (CONF-02 e SEC-ADMIN fatti in
  parallelo): conflitti solo in `PLAN.md` e `HANDOFF.md`, risolti tenendo tutto;
  2) mobile-safari 4/4 rosso anche su `main` dal merge di #168: riprodotto con il
  viewport iPhone 14, la barra degli strumenti copriva l'evento cliccato; il test ora
  tocca l'arco visibile; 3) lo script restava appeso perché Postgres ereditava lo
  stderr del chiamante: corretto.
- Cosa è cambiato: `scripts/vpt_stack.sh`; in `WORKFLOW.md` "una sessione, un
  punto", "Più agenti in parallelo" e "Stack reale"; meta di B2 in `PLAN.md`.
- Decisioni (Sohayb): meta di B2 senza il 10% fisso (riproducibilità, nessuna
  differenza statistica dal paper sui 3 log reali, baseline sui sintetici); misure
  del simulatore sullo stack reale locale, non sui database di staging o prod; B2,
  CAL-01 e UX-01 in parallelo, un agente per punto.
- Code review: il diff di #170 era già passato da `code-review` (9 + 9 rilievi
  corretti); il merge ha portato solo documenti e un test e2e. #171 non tocca il
  codice dell'app.
- Prossimo passo: B2, CAL-01 e UX-01 in tre sessioni nuove.

---

## 2026-11-24 — B1b import dal frontend tramite il server — fatto

- Branch / PR: `feat/sim-prosimos-import-ui`, verso `main` (contiene B1a, #169).
- Meta: uno scenario che l'editor non rappresenta (SIMOD) si importa dal server e si
  simula così com'è, con il report in linguaggio di business → raggiunta. Misura: test
  API 4/4 (il run arriva al motore con le stesse attese), e2e 8/8 su chromium e
  mobile-chrome, unit 4/4.
- Iterazioni: 1) endpoint e test API; 2) pannello e2e verde al primo giro; 3) gate UX:
  accenti mancanti e "1 percorso … valgono" nei messaggi del server, corretti;
  4) code review (skill `code-review`): 9 rilievi, tra cui risposte obsolete che
  ricomparivano e guasti del server che cancellavano il motivo dell'editor; tutti
  corretti, con e2e per risposta lenta, guasto del server e scenario adattato.
- Skill: `react-ui-patterns`, `code-review`. Gate UX: screenshot desktop e mobile letti.
- Decisione: i calendari FUZZY non si rifiutano per sempre: nuovo punto CAL-01.
- Prossimo passo: CAL-01.

## 2026-11-23 — B1a import Prosimos lato server — fatto

- Branch / PR: `feat/sim-prosimos-import`.
- Meta: 19/19 scenari importati nell'IR e ricompilati con gli stessi parametri,
  differenze dichiarate → raggiunta. Misura: `uv run pytest --noconftest
  tests/simulation/test_prosimos_import.py` → 61 passati. Controprova: alterando
  dell'1% la conversione dell'esponenziale il test fallisce su 19 casi.
- Iterazioni: 1) profilo dei 19 scenari: 640 durate `fix 0`, 47 orari con
  microsecondi, 48 porte d'unione, 4 calendari non usati; 2) IR esteso (durata zero,
  microsecondi) invece di riscrivere i dati; 3) prima implementazione: 44/44;
  4) code review (skill `code-review`): 9 rilievi, tutti corretti con un test ciascuno.
- Decisioni: l'IR accetta attività istantanee e orari al microsecondo, vieta arrivi a
  intervallo zero; i calendari FUZZY di SIMOD si rifiutano (DeliR non li esegue).
- Skill: `code-review`. Gate UX: non applicabile (solo backend), si applica in B1b.
- Prossimo passo: B1b.

## 2026-11-23 — CI di main verde — fatto

- Branch / PR: `claude/funny-babbage-cw4b84`, [Eng-suso/BK-GPT#168](https://github.com/Eng-suso/BK-GPT/pull/168).
- Meta: 5/5 e2e rossi su `main` (stesso shard, stessi test) → 8/8 passati in
  `simulation-escalation` e `simulation-eventlog` (chromium, locale).
- Iterazioni: 1) mock `/validation` mancante → crash `reading 'cycle'`; 2) log con
  soli completamenti: il confronto per attività spariva (difetto vero, corretto nel
  componente); 3) test fermi al copy e al wizard precedenti; 4) gate UX: messaggio
  "Calcolo il confronto…" bloccato per sempre (`isPending` su query disabilitata),
  corretto con `isLoading`.
- Gate UX: screenshot prima/dopo desktop e mobile in `docs/vpt/ux/complete-only-log/`,
  letti. Emerso il gergo nel percorso ordinario e il layout mobile: nuovo punto UX-01.
- Skill: `code-review`, verifica visiva con screenshot.
- Prossimo passo: merge della PR, poi B1 o UX-01.

## 2026-11-23 — Workflow di ingegneria — fatto

- Branch / PR: `claude/funny-babbage-cw4b84`, [Eng-suso/BK-GPT#168](https://github.com/Eng-suso/BK-GPT/pull/168).
- Cosa è cambiato: `WORKFLOW.md` (ciclo di un punto, checkpoint, regola "mangiare la
  complessità", gate UX con screenshot, skill e code review obbligatorie),
  `HANDOFF.md` (dove siamo adesso), rimando in `CLAUDE.md` e `AGENTS.md`.
- Code review: revisione manuale del diff completo. Rilievi corretti: id
  duplicati nel manifest non rilevati; `noqa` sulla riga sbagliata. CodeRabbit
  rimosso su richiesta di Sohayb: config, skill `code-review` e `autofix`; le sue
  regole ast-grep restano in `.ast-grep-rules/`, due bloccanti in CI. Verificato il
  download git di SIMOD e Prosimos (commit fissato, MD5 di `input_output_files.zip`).
- Gate UX: non applicabile, nessuna schermata cambiata.
- Prossimo passo: B1.

## 2026-11-23 — D0 dataset nel repo — fatto

- Branch / PR: `claude/funny-babbage-cw4b84`, PR verso `main`.
- Meta: tutti i dataset elencati da Sohayb nel manifest, ognuno scaricabile e
  verificato → raggiunta. Misura: `scripts/fetch_datasets.py verify` (3/3 nel
  repo) e `fetch` di BPIC 2012, BPIC 2013 e BPIC 2020 con MD5 coincidente.
- Cosa è cambiato:
  - nel repo (CC BY 4.0 e Apache-2.0): input e metriche del dataset Extraneous
    Activity Delays (Zenodo 10435849), configurazioni e log di esempio di SIMOD;
  - nella cache, con MD5 o commit fissato: output completi del paper (99,6 MB),
    reproducibility package di Camargo et al. (282,8 MB), BPIC 2012, BPIC 2013,
    repository Prosimos e SIMOD;
  - BPIC 2020 (CC BY-NC) come dataset `academic`, con `--allow-noncommercial`;
  - `tests/simulation/test_dataset_manifest.py` in CI;
  - corretto `tests/simulation/benchmark/benchmark_datasets.py`: gli uuid 4TU
    erano quelli del DOI storico e l'API rispondeva "does not exist". Ora BPIC
    2012 e 2013 si scaricano e si caricano.
- Decisioni: il repo è pubblico, quindi i dati 4TU (termini 4TU), BPIC 2020
  (non commerciale) e Prosimos (nessuna licenza upstream) restano scaricabili e
  non copiati, in attesa di conferma di Sohayb. Ambiente cloud **BK-GPT** con
  `zenodo.org` e `data.4tu.nl`.
- Prossimo passo: B1 (import Prosimos tollerante sui 19 scenari), poi B2.

## 2026-11-23 — CONF-01 conformance log ↔ BPMN — fatto (backend)

- Branch: `ccr-9b6e10c9-jmjsbm`. Prima: revisione e merge su `main` di
  `fix/p0-egress-inventory` e `claude/funny-babbage-cw4b84` (pytest 2849 passati
  con Postgres e Neo4j, vitest 822 passati, ruff, mypy, ast-grep, tsc, lint).
- Origine: audit architetturale esterno; mancava il confronto fra i casi
  eseguiti e il comportamento consentito dal modello (diverso dall'audit
  fonti ↔ modello di `agents/conformance_audit.py`).
- Cosa è cambiato:
  - `backend/eventlog/conformance.py`: BPMN → rete di Petri, token-based replay
    per variante con ricerca BFS delle transizioni silenti, fitness di Rozinat e
    van der Aalst pesata per casi, deviazioni per elemento;
  - `GET /v1/workspace/event-logs/{id}/conformance`: usa il mapping e
    l'abbinamento confermati, avvisa se il BPMN è cambiato dopo l'abbinamento.
- Misura: LoanApp (SIMOD) 500/500 casi conformi in 0,01 s; togliendo «Appraise
  property» a 3 casi, 497 conformi e le 3 deviazioni attribuite all'elemento
  giusto.
- Limiti dichiarati nel modulo: solo flusso di controllo (le condizioni sui dati
  non si valutano), join inclusivo approssimato, sottoprocesso atomico, casi
  aperti con token rimanenti.
- Gate UX: non applicabile, nessuna schermata cambiata.
- Prossimo passo: CONF-02 (vista per il consulente) oppure B1, come da piano.

## 2026-11-24 — CONF-02 vista di conformance e SEC-ADMIN — fatto

- Branch: `ccr-9b6e10c9-jmjsbm`.
- CONF-02: nuovo passo «Aderenza al processo» nel wizard degli event log, fra
  «Risorse» e «Reale contro simulato». Verdetto in parole («2 casi su 3 seguono il
  disegno»), passi saltati o fatti senza i precedenti, percorsi reali fuori dal
  disegno, attività del log senza passo, overlay sul BPMN con legenda propria
  (fino al 10% / 10–40% / oltre il 40% dei casi). Fitness e metodo solo nei
  dettagli per specialisti.
- Contratto: `cases_affected` per elemento (casi distinti), avvisi come codici con
  parametri, 409 con codice stabile (`not_mapped`, `no_model`,
  `model_not_replayable`) dal gestore comune degli errori.
- SEC-ADMIN (dall'audit): con auth accesa e senza `DELIR_ADMIN_TOKEN`, ogni client
  era amministratore. Ora fuori dallo sviluppo le operazioni amministrative
  rispondono 403; all'avvio un warning lo dice. **Attenzione al deploy**: in
  staging e prod va impostato `DELIR_ADMIN_TOKEN` per poter cancellare.
- Misura: vitest 828+ verdi, e2e `simulation-eventlog` 12/12 (chromium e
  mobile-chrome, axe WCAG 2 A/AA pulito), pytest eventlog e server verdi.
- Gate UX: screenshot desktop e mobile aperti e letti; corretta la legenda del
  disegno, che parlava ancora di scarto dei tempi.
- Review: `code-review` (10 rilievi, tutti corretti), `simplify` (4 revisori;
  saltato solo l'helper della lingua, schema già diffuso in ~10 file),
  `security-review` (nessuna vulnerabilità; il cambio di `security.py` restringe
  soltanto i permessi).
- Skill: code-review, simplify, security-review; per l'UI ui-visual-validator
  (screenshot letti) e accessibility (axe).
- Prossimo passo: B1 (import Prosimos tollerante), poi UX-01.

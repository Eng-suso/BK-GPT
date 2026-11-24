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

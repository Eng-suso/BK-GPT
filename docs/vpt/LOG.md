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

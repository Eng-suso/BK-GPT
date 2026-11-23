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

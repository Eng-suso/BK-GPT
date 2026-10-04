# Spike G1 — Prosimos 1.2.6 o 2.x

Data: 2026-10-04
Stato: chiuso, decisione presa (vedi in fondo)

## Domanda

Prima di scrivere patch su Prosimos 1.2.6, quanto della parity M1 copre già il
motore, in quale versione, e cosa resta da costruire lato DeliR?

## Metodo

`ops/prosimos/spike/contract_spike.py` esegue lo stesso mini P2P
(`p2p_mini.bpmn`: Ricevi → XOR importo → Approva → Paga) una volta per
capacità, 200 casi a run. Ogni capacità è uno scenario separato, così un
fallimento indica esattamente la sezione del contratto che il motore non regge.
Lo spike non si ferma al parser: dove possibile verifica sul log prodotto che la
capacità abbia avuto effetto (es. nessuna approvazione fuori calendario, ogni
caso instradato secondo la regola sull'importo).

- **2.1.0**: Prosimos da PyPI nel processo, Python 3.12.
- **1.2.6**: il microservizio di sviluppo (`delir-prosimos-api-dev`, Python 3.9,
  pix-framework 0.9.0) via HTTP, con la patch sincrona di DeliR.

Report grezzi: `ops/prosimos/spike/results/`.

## Risultati

| Capacità | 1.2.6 (servizio) | 2.1.0 | Verifica sul log |
| --- | --- | --- | --- |
| Scenario attuale di DeliR | ✅ | ✅ | 200 casi |
| Calendari diversi per pool | ✅ | ✅ | nessuna approvazione fuori lun–gio 10–14 |
| Uniforme, lognormale, gamma | ✅ | ✅ | run completato |
| Triangolare | ❌ 400 | ❌ `NoneType.generate_sample` | pix-framework non la deserializza |
| Attributi del caso (discreti e continui) | ✅ | ✅ | colonne `tipo`, `importo` nel log |
| Routing condizionale (`branch_rules`) | ⚠️ accettato ma **ignorato**: 96/200 casi contro la regola | ✅ ogni caso secondo la regola | importo > 5000 ⇔ Approva |
| Priorità di coda per attributo | ✅ | ✅ | premium attende meno di standard |
| Attributi che cambiano nel processo (`event_attributes`, espressioni) | ❌ assente dal log | ✅ `rischio = importo / 1000` | valore ricalcolato e coerente |
| Batch | accettato | accettato | effetto non ancora verificato |
| Seed riproducibile | non esposto | ✅ con `random.seed` + `numpy.random.seed` nel processo | stesso seed ⇒ log identico, seed diverso ⇒ log diverso |

Altro, letto dal sorgente di 2.1.0 e non provato con un run:

- distribuzioni accettate: `fix`, `expon`, `uniform`, `norm`, `lognorm`, `gamma`.
  Weibull e beta non esistono in pix-framework;
- attributi evento anche `markov` e `dtree`; attributi globali;
  `gateway_execution_limit` per i loop di rework; multitasking; calendari
  `FUZZY` (disponibilità probabilistica);
- elementi BPMN simulati: gli stessi della 1.2.6 (task, start, end, quattro
  gateway, `intermediateCatchEvent`). Nessun boundary event, nessun sottoprocesso;
- coda: FIFO di default, priorità per regole. Nessun LIFO;
- durate: per coppia attività–risorsa. Non dipendono da attributi né da fascia oraria;
- casualità: `random` e `numpy.random` globali. Nessun flusso separato per arrivi e
  servizi, quindi le common random numbers sono solo approssimate.

Vincolo di piattaforma: Prosimos 2.1.0 richiede Python `>=3.11,<3.13`. Il backend
DeliR gira su Python 3.14, l'immagine del microservizio su Python 3.9. Prosimos 2.x
non può girare né nel backend né nell'immagine attuale.

## Cosa significa per la roadmap

| Voce | Esito dello spike |
| --- | --- |
| SIM-01 distribuzioni | Fissa, esponenziale, uniforme, normale, lognormale e gamma sono **solo lavoro di adapter e UI**. Triangolare, Weibull e beta vanno tolte dalla prima versione o approssimate lato DeliR con un fit dichiarato. |
| SIM-02 calendari | Supportati già oggi: **adapter + IR + UI**. |
| SIM-30 capacità nel tempo | Ottenibile con un calendario per singola risorsa; i calendari fuzzy coprono la disponibilità probabilistica. |
| SIM-31 attributi e modifiche | Attributi del caso: già oggi. Modifiche durante il processo: **solo 2.x**. |
| SIM-34 routing condizionale | **Solo 2.x**: la 1.2.6 accetta la sezione e la ignora in silenzio. |
| SIM-12 code | Priorità sì; LIFO no. LIFO resta fuori dalla prima versione. |
| SIM-32 durate condizionali | Non native. Compilazione lato IR: il task diventa varianti dietro un XOR con `branch_rules` (richiede 2.x). |
| SIM-33 parametri per fascia oraria | Arrivi e capacità sì (calendari); durate e routing per fascia no: da compilare lato IR o da rimandare. |
| SIM-11 / SIM-35 semantica BPMN | Il normalizer resta necessario anche con 2.x. Rework con `gateway_execution_limit`; escalation e boundary da compilare nell'IR. |
| SIM-04 repliche e seed | Seed riproducibile solo se DeliR controlla il processo che chiama Prosimos. |

## Decisione

**Passare a Prosimos 2.1.0, con un runner DeliR dedicato al posto del
microservizio upstream patchato.**

Motivi:

1. routing condizionale e attributi che cambiano sono parity M1 e funzionano solo
   in 2.x; la 1.2.6 li ignora senza errore, che è il caso peggiore;
2. il microservizio upstream è ancora fissato a `prosimos ^1.2.6` su Python 3.9:
   aggiornarlo vuol dire mantenere una patch più grande su codice altrui;
3. un runner nostro (Python 3.12, `prosimos==2.1.0` fissato) espone solo ciò che
   usiamo — simulazione, log, statistiche — e aggiunge ciò che manca: **seed**
   per repliche riproducibili e log restituito nella stessa risposta;
4. resta un servizio separato, coerente con il vincolo Python 3.14 del backend.

Nessuna patch custom sulla 1.2.6.

## Prossimi passi

1. Runner `ops/prosimos/runner/`: API compatibile con l'adapter attuale
   (`/api/simulate`, `/api/simulationFile`) più `seed`; immagine Python 3.12;
   test di contratto con le fixture dello spike.
2. Adapter DeliR verso il runner dietro flag, poi default; lo spike diventa test
   di contratto in CI.
3. Dismissione di `ops/prosimos/sync-mode.patch` quando il runner è il default.

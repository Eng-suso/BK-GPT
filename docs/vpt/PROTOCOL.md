# Protocollo sperimentale del VPT (PROTO-01, esteso da PROTO-02)

Il protocollo che G3b, B3.1-B3.4, SEL-01, PERF-01 e CF-01 seguono per dire se un
componente di discovery o di simulazione è migliore di un altro. È scritto e
congelato **prima** di qualsiasi misura di G3b; cambiarlo è una decisione di Sohayb,
scritta in [`LOG.md`](./LOG.md) con data e motivo.

- Stato: scritto il 2026-11-25 (PROTO-01). Soglie, budget e modello di go/no-go
  confermati da Sohayb lo stesso giorno.
- In codice: [`tests/simulation/benchmark/protocol.py`](../../tests/simulation/benchmark/protocol.py)
  (log, divisioni, regole, guardia sugli holdout), con i test in
  [`test_protocol.py`](../../tests/simulation/benchmark/test_protocol.py).
- Lucchetto degli holdout:
  [`protocol/holdout.lock.json`](../../tests/simulation/benchmark/protocol/holdout.lock.json),
  impronta SHA-256 **`1cfaa147a37187c1a319968f200c99d1cc5918ac0795c8a95e8ee70286c35cdb`**.
  Il test `test_the_lock_digest_is_written_in_the_protocol` lega questo numero al file:
  cambiare un holdout senza cambiare questa riga fa fallire la CI.
- Secondo set di holdout (PROTO-02, §10):
  [`protocol/holdout2.lock.json`](../../tests/simulation/benchmark/protocol/holdout2.lock.json),
  impronta SHA-256 **`24974f9b11e3e66b4297105ff4684036f306a9f83351a7ad7ddae19801a7e576`**
  (`test_the_second_lock_digest_is_written_in_the_protocol`). Il primo lucchetto e il benchmark
  congelato non cambiano.

## 1. Cosa si misura

Per ogni configurazione e ogni log:

- **fedeltà**: le sei distanze di B2 (`log_distance.py`, port di `log-distance-measures`
  2.2): W1 della durata dei casi, NGD dei percorsi (3-grammi), RED, AED, CED, CAR, con
  media e intervallo al 95% su 10 repliche, seed `20261124 + replica`;
- **componenti**, dove i dati lo permettono: durate delle attività, risorse, cause delle
  attese, parametri veri del processo, effetto di un intervento ("cosa succede se");
- **costo**: tempo di discovery, tempo di simulazione, picco di memoria (PERF-01 aggiunge
  la scalabilità).

Il confronto fra due configurazioni usa la regola comune di B2
(`eval_harness.within_intervals`): una vince se i due intervalli al 95% non si
sovrappongono; altrimenti sono pari. Le mete già scritte restano decise da questa regola.

**Confronto appaiato, accanto (PROTO-02).** Gli intervalli che non si sovrappongono sono un
criterio conservativo, non un test sulla differenza. Dove le repliche sono appaiate (stesso log,
stesso seed `20261124 + replica`) si riporta accanto anche `protocol.paired_comparison`:
differenza media delle distanze, intervallo bootstrap al 95% della differenza (10.000
ricampionamenti, seed `20261125`) e p del test dei ranghi con segno di Wilcoxon, esatto a due
code. Verdetto: «a meglio» o «b meglio» se l'intervallo della differenza sta tutto da una parte
dello zero, altrimenti «pari». Esempio nei test: un miglioramento costante di 0,5 su repliche
con varianza alta è «pari» per gli intervalli e «a meglio» per il confronto appaiato. Il
confronto appaiato non cambia nessuna meta già scritta; una meta nuova che lo usa lo dichiara.

## 2. Log e categorie

Tre categorie, assegnate dalla fonte del log e verificate con le proprietà del §4:

- **osservabilità completa**: inizio e fine delle attività, risorse. Misurano
  l'accuratezza complessiva;
- **osservabilità parziale**: mancano inizi, o i casi sono tagliati dalla finestra del
  log. Misurano la robustezza quando mancano informazioni;
- **sintetici con verità nota**: generati da un modello di simulazione pubblicato.
  Misurano la correttezza matematica (parametri veri) e i "cosa succede se".

### Log di sviluppo (25)

Si usano per sviluppare, scegliere modelli, iperparametri e componenti.

| Categoria | Log | Fonte | Licenza |
| --- | --- | --- | --- |
| osservabilità completa | AcademicCredentials, BPIC 2012 W, BPIC 2017 W | `datasets/extraneous-delays/inputs/real-life`, train e test del paper | CC BY 4.0, nel repo |
| osservabilità parziale | BPIC 2012 (log completo), BPIC 2013 incidents | 4TU, `scripts/fetch_datasets.py` | 4TU General Terms, solo cache |
| sintetici con verità nota | Insurance_Claims, Loan_Application, Pharmacy, Procure_to_Pay, ognuno con 0, 1, 3, 5 timer e 5 timer "after" (20 log) | `datasets/extraneous-delays/inputs/synthetic`, verità nei file `.json` e `.bpmn` | CC BY 4.0, nel repo |

**Nessun log escluso.** BPIC 2013 incidents resta: le metriche che non permette di
validare sono dichiarate NOT VALIDATED (§4), le altre si misurano. Questo supera la
marcatura "non adatto al confronto A→B" di SIM-36b, che resta come nota nel benchmark.

Non sono log separati del benchmark, e il motivo non dipende da nessun risultato:

- `cvs_pharmacy` del pacchetto Camargo 2022 viene dallo stesso modello di Pharmacy (stesse
  attività): è una seconda estrazione di un log di sviluppo, non un processo nuovo;
- le copie di BPIC 2012 W e 2017 W nel pacchetto Camargo sono gli stessi log del paper;
- `datasets/simod/event-logs` (Insurance_Claims, LoanApp_simplified) sono gli esempi di
  configurazione di SIMOD, sugli stessi processi dei sintetici;
- BPIC 2020 (CC BY-NC) non entra: il criterio, dichiarato qui e uguale per tutti, è che i
  numeri del benchmark possano sostenere affermazioni commerciali (H1). Resta per la
  ricerca accademica come da `datasets/README.md`.

### Log holdout (6)

Indipendenti, **mai usati per scegliere** algoritmi, configurazioni o soglie. Si aprono una
volta sola, a selezione chiusa, per la valutazione finale (§3).

| Log | Categoria | Organizzazione | Fonte | Divisione |
| --- | --- | --- | --- | --- |
| Production | osservabilità completa | azienda manifatturiera | pacchetto Camargo 2022 (Zenodo, CC BY 4.0) | test pubblicato dal pacchetto |
| ConsultaDataMining 2016-18 | osservabilità completa | università colombiana | pacchetto Camargo 2022 | test pubblicato |
| PurchasingExample | osservabilità completa (simulato, modello non pubblicato) | esempio di acquisti | pacchetto Camargo 2022 | test pubblicato |
| confidential_2000 | sintetico con verità nota (`ConfidentialProcessModel.bpmn`) | modello riservato | pacchetto Camargo 2022 | test pubblicato |
| BPIC 2015 Municipality 1 | osservabilità parziale | comune olandese | 4TU, General Terms | metà dei casi per inizio |
| BPIC 2011 Hospital log | osservabilità parziale | ospedale universitario olandese | 4TU, General Terms | metà dei casi per inizio |

## 3. Holdout: scelta, congelamento, apertura

**Criteri**, dichiarati prima di aprire qualsiasi log:

1. pubblico, scaricabile con un hash fisso, con una licenza che permette di usarne i numeri;
2. organizzazione e processo diversi da ogni log di sviluppo (BPIC 2012 e 2017 vengono
   dalla stessa banca: un altro log di quella banca non sarebbe indipendente);
3. mai letto da codice di DeliR prima del 2026-11-25 (verificato con `git grep`);
4. le tre categorie coperte;
5. dimensioni gestibili nel budget del §6.

Limite dichiarato: ConsultaDataMining potrebbe venire dalla stessa università di
AcademicCredentials. È indipendente come processo, non garantito come organizzazione: il
risultato su questo log si riporta con la nota.

**Cosa è stato letto per sceglierli:** solo i nomi dei file, le dimensioni, le licenze e,
per confidential, la presenza delle informazioni di simulazione nel BPMN (306 elementi
`qbp:`); per `cvs_pharmacy` (che non è un holdout) i nomi delle attività. Nessun evento
di un log holdout è stato letto.

**Congelamento** (2026-11-25, prima di qualsiasi misura di PROTO-01 e di G3b):
`tests/simulation/benchmark/protocol_freeze.py` ha scritto per ogni file il suo SHA-256 e
la dimensione nel lucchetto; i due log 4TU sono anche nel manifest con l'MD5. Nel repo
pubblico ci sono solo gli hash: i log stanno nella cache di `fetch_datasets`. Lo script non
riscrive un lucchetto esistente senza `--refreeze`.

```bash
uv run python scripts/fetch_datasets.py fetch camargo-2022-reproducibility bpic2015-municipality1 bpic2011-hospital
uv run pytest --noconftest -q tests/simulation/benchmark/test_protocol.py   # compreso il controllo degli hash nella cache
```

**Guardia.** Il codice di selezione non può leggere un holdout:

- `protocol.selection_phase()` racchiude ogni punto d'ingresso che sceglie qualcosa
  (G3b, B3.x, SEL-01). Un audit hook di Python rifiuta con `HoldoutAccessError`
  l'apertura in lettura di: ogni file che porta il nome di un log holdout, in qualunque
  cartella e con qualunque estensione da log (anche una copia convertita, per esempio
  `production.parquet`); ogni file ricavato da un holdout (`Production_1.csv`,
  `confidential_2000_modif.bpmn`); ogni file dei dataset holdout, archivio compreso (tutti
  i 715 file del pacchetto Camargo, compresi i log simulati dai modelli addestrati sugli
  holdout); un collegamento simbolico o fisico con un nome innocuo a un file holdout della
  cache. La guardia è attiva per tutti i test del benchmark (`conftest.py`);
- la fase vale per il thread che la apre: `final_evaluation` in un thread non apre gli
  holdout negli altri, e un thread nuovo parte chiuso. La guardia non passa ai
  sottoprocessi (SIMOD, runner): a loro il codice di selezione passa solo percorsi di log
  di sviluppo. Una copia con un nome innocuo fatta fuori dal processo non si riconosce:
  la difesa è il test sui nomi qui sotto, più la regola che gli holdout si scaricano solo
  per la valutazione finale;
- `test_selection_code_does_not_name_a_holdout_log` fallisce se un file di
  `tests/simulation`, `backend/simulation`, `backend/eventlog` o `scripts` nomina un log
  holdout o il suo dataset; gli unici ammessi sono il lucchetto, lo script che lo scrive e
  il test. Copre ciò che l'hook non vede: una libreria che apre i file da codice nativo;
- `test_selection_code_reading_a_holdout_fails` prova la guardia con `open`, `pathlib`,
  `gzip`, `zipfile`, `os.open`, `shutil.copy` e il lettore CSV del benchmark.

**Apertura.** Solo con `protocol.final_evaluation(<impronta del lucchetto>)`, una volta,
quando la selezione è congelata (configurazioni, iperparametri e soglie scritti in
`LOG.md`). L'apertura si scrive in `LOG.md` con data, commit e configurazioni valutate.
Sugli holdout si applicano le stesse regole del §4, calcolate all'apertura: una metrica
non identificabile su un holdout è NOT VALIDATED, il log resta.

## 4. Identificabilità: NOT VALIDATED

Una metrica che i dati non permettono di identificare si dichiara **NOT VALIDATED** con il
motivo, non si stima per forza. Il verdetto viene da proprietà calcolate sui dati, mai da un
modello, con le stesse soglie per ogni log (`protocol.properties` e
`protocol.identifiability`).

**Proprietà** (A = train, B = test):

- casi in train, validazione e test; eventi;
- copertura dell'inizio e della risorsa sugli eventi;
- casi di B **tagliati a destra**: quota di casi di B la cui ultima attività non è fra
  quelle con cui finisce il 95% dei casi maturi di A (iniziati nella prima metà di A),
  meno la stessa quota fra i casi maturi (il 5% che il 95% lascia fuori per costruzione);
- casi di B **tagliati a sinistra**: lo stesso con l'attività iniziale e i casi della
  seconda metà di A;
- rapporto fra il ritmo degli arrivi di B e quello di A.

**Regole:**

| Metrica | NOT VALIDATED se |
| --- | --- |
| tutte | meno di 30 casi in train o in test |
| W1 durata dei casi, NGD percorsi, RED | più del 5% dei casi di test tagliati a destra o a sinistra |
| AED, CED | (solo la regola dei 30 casi: sono istanti osservati nella finestra) |
| CAR arrivi | più del 5% tagliati a sinistra, o arrivi di B oltre 2 volte (o sotto la metà) di quelli di A |
| durate delle attività | inizio su meno del 95% degli eventi |
| risorse | risorsa su meno del 95% degli eventi |
| cause delle attese, parametri veri, cosa succede se | log non sintetico: la verità c'è solo nei sintetici |

**Misura sui log di sviluppo** (`protocol_properties.py`, 2026-11-25; tabella completa in
[`protocol/identifiability.md`](../../tests/simulation/benchmark/protocol/identifiability.md),
numeri in `protocol/development.json`):

| Log | Casi fit / validazione / test | Inizio | Tagliati destra / sinistra | Arrivi B/A | NOT VALIDATED |
| --- | --- | --- | --- | --- | --- |
| AcademicCredentials | 318 / 80 / 398 | 100% | 2,5% / 0,5% | 0,98 | cause delle attese, parametri veri, cosa succede se |
| BPIC 2012 W | 2424 / 606 / 2976 | 100% | 0,7% / 0% | 1,08 | come sopra |
| BPIC 2017 W | 5922 / 1480 / 7376 | 100% | 0,3% / 0% | 0,94 | come sopra |
| BPIC 2012 | 5234 / 1309 / 6544 | 43% | 6,2% / 0% | 1,02 | W1, NGD, RED (6% tagliati); durate delle attività (inizio sul 43%); verità |
| BPIC 2013 incidents | 3021 / 755 / 3778 | 0% | 37% / 0% | 204,6 | W1, NGD, RED (37% tagliati); CAR (arrivi ×204: non è lo stesso flusso); durate delle attività (nessun inizio); verità |
| 20 sintetici | 400 / 100 / 500 ciascuno | 100% | 0% / 0% | 0,98-1,00 | nessuna |

Su BPIC 2013 incidents restano validi AED, CED e risorse. Le distanze non validate si
calcolano e si salvano lo stesso, marcate NOT VALIDATED: non contano per vincere né per
perdere.

**Iterazione della regola** (prima di ogni misura di G3b): la prima versione contava come
tagliato ogni caso che non finisce fra le attività del 95%: dava 5-6% anche sui log completi
del paper (AcademicCredentials 6%, BPIC 2012 W 5%), per costruzione. Ora conta l'eccesso
sui casi maturi. La regola degli arrivi è stata aggiunta vedendo BPIC 2013: un rapporto ×2
fra due metà dello stesso log non è un flusso stazionario, ed è dichiarata per tutti.

**Limiti dichiarati.** Il taglio a sinistra si stima dai casi della seconda metà di A: in
un log che è tutto una foto (come BPIC 2013) anche quelli possono essere tagliati, e la
stima resta bassa; per questo c'è la regola degli arrivi. "Inizio presente" vuol dire che
il campo c'è: nei CSV del paper un'attività con inizio uguale alla fine conta come
osservata.

## 5. Divisione train / validazione / test

- **Test:** dove la fonte lo pubblica, quello della fonte (i 3 log del paper, i 4 holdout
  del pacchetto Camargo); altrimenti B = la seconda metà dei casi per inizio, come SIM-36
  (`run_baseline.split_in_half`). Per i 20 sintetici: metà dei casi per inizio.
- **Validazione:** l'ultimo 20% dei casi del train per inizio (`protocol.train_validation`,
  deterministico, casi mai spezzati). Si sceglie qui: configurazioni, iperparametri,
  componenti, soglie.
- **Fit:** il resto del train. La configurazione scelta si riaddestra sull'intero train e
  si misura sul test una volta.
- Il test dei log di sviluppo è già stato guardato (B2, SIM-36b, G3): per questo esistono gli
  holdout. Una vittoria che vale solo sui log di sviluppo non è una generalizzazione.

## 6. Budget di calcolo

Lo stesso per ogni configurazione, misurato sulla macchina di riferimento (4 vCPU, 16 GB,
la sessione cloud dello stack di `scripts/vpt_stack.sh`):

- discovery: al massimo **2 ore** di tempo reale e **12 GB** di picco per configurazione e
  log (G3: SIMOD al massimo 45 minuti su BPIC 2017 W);
- ricerca degli iperparametri: al massimo **20 valutazioni sulla validazione** per
  configurazione e log, uguali per tutti i candidati;
- simulazione: 10 repliche con tanti casi quanti il test, al massimo **10 minuti** per
  replica;
- G3b in tutto: al massimo **120 ore** di tempo reale; oltre, decide Sohayb;
- fuori budget = risultato "fuori budget" con tempo e memoria misurati: conta come
  sconfitta su tutte le metriche, il log resta;
- tempi e memoria si riportano accanto alla fedeltà (PERF-01).

## 7. Go/no-go per componente

Ogni componente (arrivi, attese, control flow, risorse, motore) si decide con una scheda
scritta in `LOG.md` **prima** della misura:

| Campo | Contenuto |
| --- | --- |
| Ipotesi | cosa deve migliorare e perché |
| Base | la configurazione da battere: "B = A" e la migliore di G3 (SIMOD fissi + ritardi estranei) |
| Metrica primaria | una delle metriche del §1, scelta prima |
| Metriche di guardia | le altre metriche di fedeltà, tempo e memoria |
| Log | quelli del protocollo dove la metrica primaria è identificabile |

- **GO** se, prima sulla validazione e poi sul test dei log di sviluppo: la metrica
  primaria vince (intervalli separati) sulla maggioranza dei log dove è identificabile e
  non perde su nessuno; nessuna metrica di guardia perde (intervalli separati) su più di un
  log; tempo e memoria entro il budget e al massimo il doppio della base; il modello che
  produce supera VAL-01.
- **NO-GO** se una delle condizioni manca.
- **NOT VALIDATED** se la metrica primaria è identificabile in meno di 2 log: non si
  decide, si cerca un log che la renda identificabile.
- **Conferma sugli holdout**, alla fine di G3b, una volta: un GO resta GO se sugli
  holdout dove la metrica primaria è identificabile non perde contro la base; altrimenti
  diventa NO-GO e lo si scrive. Nessun ritorno alla selezione dopo l'apertura.
- **Prodotto.** Un GO di ricerca entra nel prodotto solo se LIC-01 ammette il codice e la
  licenza: altrimenti resta nell'ambiente di ricerca (binario Ric).

## 8. Riproducibilità

Ogni misura di G3b scrive: commit, impronta del lucchetto, configurazione, seed, log,
divisione, versione dei componenti esterni e dei dati (MD5 o commit del manifest), tempi e
memoria; metriche senza orari, così che stesso seed e stessi dati diano lo stesso file.

```bash
uv run python scripts/fetch_datasets.py fetch bpic2012 bpic2013-incidents
uv run python tests/simulation/benchmark/protocol_properties.py   # §4, gira dentro selection_phase
uv run pytest --noconftest -q tests/simulation/benchmark/test_protocol.py
```

## 9. Per G3b

- I punti d'ingresso girano in `protocol.selection_phase()` e leggono i log da
  `protocol.development_logs()`.
- La scelta si fa sulla validazione (`protocol.train_validation`), il test si guarda una
  volta per configurazione scelta, gli holdout una volta alla fine.
- Le schede del §7 si scrivono in `LOG.md` prima di lanciare le misure.
- Le metriche NOT VALIDATED del §4 si riportano nelle tabelle, marcate, e non contano.

## 10. La seconda collezione: il Research Radar (PROTO-02)

Il radar (`collection: radar` nel manifest, [`RESEARCH_RADAR.md`](./RESEARCH_RADAR.md)) è una
collezione separata. Qui ogni sua voce riceve un ruolo, una volta, dopo l'inventario di RAD-01 e
prima di qualsiasi uso: **sviluppo** (si usa per sviluppare e scegliere), **holdout 2** (secondo
set, chiuso come il primo), **escluso** (non si usa, con il motivo) o **codice** (repository senza
log propri da valutare: si esegue come baseline o strumento). I log di sviluppo del §2 e i 6
holdout del §2 non cambiano.

**Inventario** (RAD-01): `tests/simulation/benchmark/radar_inventory.py`, report in
[`radar/inventory.md`](../../tests/simulation/benchmark/radar/inventory.md). Per ogni file del radar,
anche dentro gli archivi: SHA-256 confrontato con ogni file di `datasets/`, con i log di sviluppo
in cache e con i due lucchetti; nome confrontato con i log di sviluppo e con gli holdout; contenuto
(attività e id dei casi) confrontato con i log di sviluppo e con le altre voci. Gira dentro
`selection_phase()`: un file con il nome di un holdout si marca e se ne calcola solo l'impronta
(`protocol.fingerprint`), mai gli eventi.

### Sovrapposizioni trovate (RAD-01)

| Attesa | Verifica |
| --- | --- |
| BPIC 2012/2017 dentro ProCause | **No come file**: il repository ha solo `data/bpic2012/.gitkeep` e `data/bpic2017/.gitkeep`; il notebook di pulizia li legge da fuori. Gli esperimenti di ProCause su quei log sono esperimenti sui log di sviluppo. |
| BPIC 2012 W e 2013 nella copia di Helpdesk | **Sì**: `bpi_12_w.csv` e `bpi_12_w_no_repeat.csv` hanno tutti i casi di BPIC 2012 W di sviluppo (attività ricodificate come numeri); `bpi_13_incidents.csv` ha gli stessi casi di BPIC 2013 incidents. In più `env_permit*.csv`: il permesso ambientale (WABO) del progetto CoSeLoG, lo stesso progetto dei comuni di BPIC 2015. |
| Log di Camargo in AgentSimulator e nel BPS Quality Framework | **AgentSimulator**: solo `LoanApp` (processo Loan_Application di sviluppo) e i suoi simulati. **BPS Quality Framework**: AcademicCredentials train/test identici per hash a quelli di sviluppo; BPIC 2012 e 2017 (W) con gli stessi casi dello sviluppo; LoanApp e Procure2Pay sono i processi sintetici di sviluppo; i simulati di SIMOD e ServiceMiner di questi; in più **CallCenter**, che non è in nessun altro posto. Nessun holdout del primo set. |
| Log di Camargo altrove | **Kronos** (`tests/assets`): 6 file con i nomi di Production e PurchasingExample (anche dentro due zip): marcati, non aperti, esclusi. Nessuno coincide per impronta con il primo lucchetto (sono estratti diversi). |
| Sepsis e Hospital Billing non dall'ospedale di BPIC 2011 | **Verificato sui metadati 4TU** (nessun holdout aperto): BPIC 2011 è il log di un *ospedale accademico* olandese (van Dongen, 2011); Sepsis viene dall'ERP di *un ospedale* e Hospital Billing dai moduli finanziari dell'ERP di *un ospedale regionale*, tutti e due di Mannhardt. Organizzazione diversa da BPIC 2011. Sepsis e Hospital Billing sono trattati come la stessa organizzazione (stesso autore, stesso ERP): stanno insieme dalla stessa parte (sviluppo). Limite: i metadati non nominano gli ospedali. |
| Altre copie | DAS-RP contiene estratti CSV di BPIC 2019, Sepsis e Road Traffic Fines (stessi casi) e un sintetico (`data_attribute_log`) sul processo Loan_Application di sviluppo; `bpic-ocel2` contiene BPIC 2017 e 2019 in OCEL (stessi eventi di `bpic2017-full` e `bpic2019`). |

### Ruolo di ogni voce

| Voce | Ruolo | Motivo |
| --- | --- | --- |
| `bps-quality-framework` | sviluppo, tranne CallCenter (holdout 2) | copie e simulati dei log di sviluppo (stessi processi, stessi casi): riferimento esterno per le distanze, non log indipendenti; CallCenter è l'unico processo nuovo |
| `simbank` | sviluppo | generatore con interventi e confondenti per CF-01 e B7 |
| `procause` | codice | nessun log nel repository; i suoi esperimenti usano BPIC 2012/2017 (sviluppo) e SimBank |
| `bpic2019` | sviluppo | procurement per RAD-02, scalabilità per PERF-01 (1,6 M eventi) |
| `bpic2018` | sviluppo | pubblica amministrazione per RAD-02, cambi annuali per B8, PERF-01 |
| `bpic2017-full` | sviluppo | stessi casi di BPIC 2017 W di sviluppo, stessa banca di BPIC 2012: non indipendente |
| `sepsis-cases` | sviluppo | sanità per RAD-02; ospedale diverso da BPIC 2011 (sopra) |
| `hospital-billing` | sviluppo | sanità per RAD-02; stessa organizzazione di Sepsis: non può fare da holdout contro di lui |
| `road-traffic-fines` | holdout 2 | pubblica amministrazione indipendente da ogni log di sviluppo (polizia locale italiana); la copia di DAS-RP è chiusa con lui |
| `helpdesk` | sviluppo per `helpdesk.csv` (solo ricerca); escluso il resto | `helpdesk.csv`: assistenza per RAD-02, ma senza licenza: i suoi numeri non sostengono affermazioni commerciali (H1) e non può essere holdout; `bpi_12_w*` e `bpi_13_incidents` sono copie dei log di sviluppo; `env_permit*` esclusi: stesso progetto (CoSeLoG) dei comuni di BPIC 2015, forse lo stesso comune dell'holdout Municipality 1, e non si può verificare senza aprirlo |
| `ocel-container-logistics`, `ocel-order-management`, `ocel-procure-to-pay`, `ocel-state-aware`, `ocel-standard-collection`, `ocel-lrms-simulated` | sviluppo | object-centric per VPT-07 e OC-01; fuori dal benchmark piatto di G3b |
| `ocel-steel-logistics` | sviluppo | unico OCEL reale (acciaieria) per VPT-07 e OC-01 |
| `bpic-ocel2` | sviluppo | BPIC 2014 (Rabobank) e 2016 (UWV) per OC-01; BPIC 2017 e 2019 sono gli stessi log di `bpic2017-full` e `bpic2019`. I BPIC 2015 non sono nel manifest |
| `existential-drifts`, `cdrift-set`, `cdlg-drift-val` | sviluppo | sintetici con drift noti per DRIFT-01 e B8 |
| `at-kde` | sviluppo | il codice degli arrivi per B3.1; `LoanAppInflation` è il processo Loan_Application di sviluppo |
| `kronos-waiting-time` | codice; esclusi i file con i nomi del primo set | log di prova del codice; quelli con il nome di un holdout non si aprono |
| `agentsimulator` | sviluppo | baseline per G3b e B3.4; `LoanApp` è un processo di sviluppo |
| `prosit` | codice | nessun log nel repository |
| `das-rp` | sviluppo, tranne l'estratto di Road Traffic Fines (holdout 2) | baseline per B3.3; estratti di BPIC 2019 e Sepsis (sviluppo) e un sintetico sul processo Loan_Application |
| `powl`, `cdrift-evaluation`, `simoc`, `declare-log-generator`, `simpy`, `salabim`, `queuesim` | codice | strumenti; i log di prova di `cdrift-evaluation` (Ceravolo, Ostovar) sono sintetici con drift per DRIFT-01 |

### Secondo set di holdout

Scelto dopo l'inventario e prima di ogni uso dei log del radar, con i criteri del §3 (pubblico
con hash fisso e licenza che permette di usarne i numeri; organizzazione e processo diversi da
ogni log di sviluppo, del primo set e del radar dichiarato di sviluppo; mai usato da DeliR per
sviluppare; dimensioni nel budget del §6). Congelato il 2026-11-25 da
`protocol_freeze.py --set 2`, prima di qualsiasi misura su questi log.

| Holdout | Categoria | Organizzazione | Fonte | Divisione | Cosa conosciamo (RAD-01, prima del congelamento) |
| --- | --- | --- | --- | --- | --- |
| CallCenter | osservabilità completa | call center (origine non documentata nel pacchetto) | BPS Quality Framework, Zenodo 12126071, Apache-2.0 | train e test pubblicati (una settimana ciascuno) | 260.889 / 260.890 casi, ~450.000 eventi a parte, 19 attività, ~2.700 risorse, gennaio 2008 |
| Road Traffic Fines | osservabilità parziale | polizia locale italiana | 4TU, General Terms | metà dei casi per inizio | 150.370 casi, 561.470 eventi, 11 attività, 2000-2013, nessun inizio |

- **Chiusi con loro:** i simulati, i modelli e le misure di CallCenter nel pacchetto (per nome,
  `CallCenter_*`) e i quattro archivi del pacchetto che li contengono; l'estratto CSV di Road
  Traffic Fines in DAS-RP (`Trafic`). Il resto dei due pacchetti resta di sviluppo
  (`closes_dataset: false` nel lucchetto): la guardia chiude i file, non la cartella.
- **Sintetico con verità nota:** nessun sintetico pubblicato del radar è indipendente dai
  processi di sviluppo (quello di DAS-RP è Loan_Application; i drift sono di DRIFT-01). La
  categoria nel secondo set la coprono le aziende di GT-01 con il To-Be nascosto.
- **Cosa è stato letto per sceglierli:** nomi, dimensioni, licenze, metadati 4TU e i conteggi
  dell'inventario qui sopra (casi, eventi, attività, periodo, risorse), calcolati da RAD-01 su
  tutto il radar prima del congelamento. Nessun modello, configurazione o soglia è stato scelto
  su questi log; dopo il congelamento l'inventario non li apre più.
- **Limiti dichiarati:** l'origine di CallCenter non è documentata nel pacchetto: indipendente
  come processo e come settore, organizzazione non verificabile. Le aziende del radar dichiarate
  di sviluppo restano un rischio se un holdout futuro venisse da una di loro: si controlla qui
  prima di aggiungerlo.
- **Guardia e apertura:** la stessa del §3. `final_evaluation(<impronta>)` apre solo il set
  di quell'impronta: aprire il primo set non apre il secondo, e viceversa. Il secondo set si apre
  una volta, alla fine del punto che lo usa (RAD-02), a selezione chiusa.

## 11. Metriche di CF-01 (PROTO-02)

Una copertura del 90% si ottiene anche con intervalli enormi. Per ogni insieme di interventi con
verità nota (`protocol.counterfactual_metrics`) si riportano insieme:

- **copertura**: quota di Δ KPI veri dentro l'intervallo al 95% (la meta di CF-01);
- **ampiezza**: media dell'intervallo, in unità del KPI e relativa al KPI di partenza;
- **errore puntuale**: media di |Δ previsto − Δ vero|, assoluta e relativa al KPI di partenza;
- **direzione**: quota di interventi con il segno del Δ previsto giusto, contata solo dove
  l'effetto vero è almeno l'**1%** del KPI di partenza (`DIRECTION_MIN_EFFECT`, *proposta*):
  sotto, la direzione è rumore.

Nei test: due modelli con la stessa copertura del 100%, uno con intervalli larghi 1.000 e la
direzione sbagliata, l'altro largo 5 con la direzione giusta, si distinguono su ampiezza,
errore e direzione. La validità sotto le ipotesi del generatore non è validità reale: per quella
servono i pilot PV (`RESEARCH_RADAR.md`).

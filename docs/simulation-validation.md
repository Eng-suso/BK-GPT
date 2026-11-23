# Validazione del simulatore contro un Event Log

Il passo **Reale contro simulato** mostra un report aggregato per il gruppo di
repliche selezionato. Ogni run completato resta ispezionabile separatamente.
L'endpoint `GET /v1/workspace/event-logs/{id}/validation?run_ids=...` accetta
solo run completati dello stesso processo, gruppo e revisione dello scenario.

## Definizioni dei KPI confrontabili

- **Cycle osservabile:** ultima fine del caso meno primo inizio registrato.
- **Attesa fra attività:** somma delle differenze positive fra l'inizio di
  un'attività e la massima fine delle attività precedenti nel caso.
- **Lavorazione:** somma delle durate inizio-fine degli eventi del caso.
- **Throughput:** casi divisi per l'arco fra il primo inizio e l'ultima fine.
- **Attesa prima della prima attività:** mostrata a parte per le simulazioni.
  Non entra nel confronto quando il log reale non registra l'abilitazione.

La diagnostica di una singola replica usa lo stesso endpoint e le stesse
definizioni della tabella aggregata per cycle, attesa fra attività,
lavorazione e throughput. La durata completa dal primo `enable_time` rimane
nel risultato grezzo del simulatore, ma non è affiancata al cycle osservabile
del log. Nella tabella delle attività, l'attesa iniziale reale senza
`enable_time` è segnata come non osservabile, non come zero.

Questa attesa fra attività comprende code e ritardi esterni. Non è una misura
di sola coda risorsa. Con attività parallele, la somma di attesa e lavorazione
può superare il cycle osservabile. Il report richiede un timestamp di inizio
per ogni evento: non produce risultati parziali se mancano.

## Statistica e distanze

Per ogni KPI il server calcola una statistica per replica, poi media, bias
rispetto al log, errore assoluto medio e intervallo t al 95% della media. Il
log reale è trattato come riferimento fisso: l'intervallo non incorpora la sua
incertezza campionaria. P50 e P90 della tabella sono medie dei percentili
per replica; sono riportati anche i percentili di tutti i casi simulati uniti.
Con `R` repliche, l'intervallo è `media ± t(0,975; R−1) × s / √R`, dove `s` è
la deviazione standard delle `R` statistiche di replica. Seed distinti e
inizio comune rendono le repliche confrontabili; non quantificano
l'incertezza di campionamento del log reale.

Le distanze vengono calcolate *prima* per ogni replica e poi aggregate:

- **Cycle W1:** Wasserstein-1 fra le distribuzioni empiriche dei cycle
  osservabili, in secondi: l'integrale da 0 a 1 della differenza assoluta
  fra le rispettive funzioni quantile empiriche.
- **NGD a 2 grammi:** differenza normalizzata fra le frequenze delle coppie
  consecutive di attività, includendo inizio e fine traccia. I nomi delle
  attività sono ricondotti agli elementi BPMN confermati nel mapping. La
  formula è `Σ_g |n_reale(g) − n_simulato(g)| / (Σ_g n_reale(g) + Σ_g n_simulato(g))`.

Il report avverte se i numeri di casi differiscono o il mapping ha escluso
righe. Non attribuisce automaticamente una soglia universale di validità.

## Inizio del run e calendari

Il motore usava l'istante di esecuzione del worker quando `start_date` era
assente. Con un calendario 09:00–17:00, le repliche lanciate alle 15:36
attraversavano la notte; quelle lanciate alle 10:24 finivano prima della
chiusura, pur avendo la stessa configurazione. Il tempo `end-start` di una
attività include la pausa fuori orario e quindi gonfiava anche la
"lavorazione" misurata dal log del motore.

I nuovi run fissano `start_date` alla mezzanotte UTC del giorno di creazione
quando l'utente non ne specifica una. La data viene salvata nella richiesta;
il calendario determina l'ora effettiva del primo arrivo. Tutte le repliche
di un gruppo condividono questa data. Il report aggregato nasconde i KPI dei
run precedenti senza data fissata e chiede di rilanciarli. Un run con data
fissata può comunque attraversare chiusure se l'orizzonte è lungo: in quel
caso vanno confrontati periodi e calendari coerenti con il log reale.

## Limiti da verificare prima di usare il report per decisioni

Se il log di riferimento ha calibrato lo stesso scenario, il risultato misura
aderenza ai dati di calibrazione. Per una valutazione predittiva serve un log
indipendente, idealmente un periodo successivo definito prima della taratura.
Il report non include ancora le distanze temporali RED/CED/CAR del framework
di Chapela-Campa et al.; richiedono finestre, fuso orario e origine temporale
allineati. Una bassa distanza AS-IS da sola non valida l'effetto di un
intervento what-if.

Riferimenti: Chapela-Campa et al., *Can I Trust My Simulation Model?* (BPM
2023); Law, *Statistical Analysis of Simulation Output Data* (WSC 2015).

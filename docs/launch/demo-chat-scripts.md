# Copioni delle chat della demo (da approvare)

Processo: "Gestione richiesta di acquisto" di Vetrano Industriale S.p.A.
(`e2e/launch-media/data/demo.bpmn`). Fonti: le tre interviste del golden set
`esaote_ciclo_passivo` (Laura Conti, Ufficio Tecnico; Paolo Marchetti,
Manutenzione; Francesca Neri, Ufficio Acquisti). Numeri: run Prosimos in
`demo-runs.json` (360 richieste, seed fisso).

Regole:

- il consulente scrive come a un collega: una richiesta per messaggio, frasi
  corte, nomi di persone e documenti, nessun nome di funzione del prodotto;
- DeliR risponde in markdown, in streaming come in produzione: cita le fonti
  per nome, dice cosa manca e non lo inventa, separa fatti, ipotesi e valori
  simulati, nessun entusiasmo;
- ogni testo tra « » e' una citazione alla lettera (lo verifica
  `scripts/launch_media_demo_quotes.py`).

## S02 · Nuovo incarico

**Consulente** — Nuovo incarico: Vetrano Industriale, acquisti indiretti. Referente Laura Conti, responsabile dell'Ufficio Tecnico.

**DeliR**

```markdown
Ho aperto il cliente **Vetrano Industriale S.p.A.** e il progetto **Acquisti indiretti**, con Laura Conti come referente.

Per partire mi servono le fonti: interviste, procedure o mail di chi lavora nel processo. Quando le carichi, estraggo chi fa cosa e ti segnalo dove le versioni non tornano.
```

## S07 · Dalle interviste alla bozza

**Consulente** — Ho caricato le interviste a Laura, Paolo e Francesca. Ricostruisci l'As-Is senza mettere niente che nessuno dice.

**DeliR**

```markdown
Ho letto le tre interviste ed estratto **38 affermazioni**, ognuna con la sua frase.

**Il processo**
- La richiesta nasce nel reparto e arriva ad Acquisti per mail: Paolo, «Mail. Sempre mail, a Laura.»
- Acquisti verifica se e' lavorabile e, se manca qualcosa, la rimanda indietro: Francesca, «Leggo e verifico se e' lavorabile.»
- Non tutte le richieste passano dal responsabile: Francesca, «Sopra una certa cifra devo chiedere una autorizzazione al mio responsabile» e «Dipende dall'importo e dal tipo di acquisto.»

**Da chiarire prima del workshop**
- **Divergenza:** chi regolarizza un acquisto urgente. Laura: «So che poi la parte di carta viene messa a posto dopo, ma non so da chi.» Francesca: «La parte di ordine si', la faccio io.»
- **Lacuna:** nessuna fonte dichiara la soglia di autorizzazione. Non la metto nel modello e te la chiedo.
```

## S09 · Confronto con le fonti

**Consulente** — Controlla la bozza contro le interviste. Dimmi cosa non regge.

**DeliR**

```markdown
**11 elementi su 14 hanno una citazione.** Tre no:

| Elemento | Perche' non ha fonte |
| --- | --- |
| Integra la richiesta | Francesca dice che rimanda indietro le richieste, nessuno descrive chi le completa |
| Comunica il rifiuto | Nessuna fonte racconta cosa succede quando l'autorizzazione e' negata |
| Richiesta respinta | Esito del ramo di rifiuto |

Li tengo come **ipotesi del consulente**, non come fatti. Ti propongo di verificarli con Laura nel workshop.
```

## S10 · Review: dove si ferma il processo

**Consulente** — Perche' le richieste si fermano su "Valuta la richiesta di spesa"?

**DeliR**

```markdown
**Non e' la valutazione: e' l'attesa.** E riguarda solo le richieste sopra soglia.

Francesca: «Se e' fuori, possono essere giorni.» e «Non c'e' un sostituto formale».

Nella simulazione As-Is una richiesta su tre passa dal responsabile e li' aspetta in media **3g 2h**. Il processo intero dura in media **1g 15h**, ma una richiesta su dieci supera i **5 giorni**.

**Cosa e' evidenza e cosa no**
- Dalle fonti: serve l'autorizzazione sopra una soglia, il responsabile puo' mancare per giorni, nessuno lo sostituisce.
- Scelte mie, nello scenario: quante richieste superano la soglia (un terzo: la soglia nessuno la dice), quando c'e' il responsabile (un'ora il martedi' e il giovedi'), volume e costi.
```

## S16 · Ipotesi To-Be

**Consulente** — Cosa cambieresti, partendo da quello che chiedono loro?

**DeliR**

```markdown
**Dalle interviste emergono due richieste precise**, entrambe di Francesca:

1. **Richiesta completa all'origine.** «Farei in modo che la richiesta nasca gia' completa, con i campi obbligatori.»
2. **Autorizzazione visibile e tracciabile.** «E vorrei che l'autorizzazione fosse una cosa che si vede, non una mail che aspetto.»

**Aggiungo un'ipotesi mia da testare:** una delega quando il responsabile non c'e', perche' Francesca segnala che oggi «Non c'e' un sostituto formale». La delega non l'ha chiesta nessuno.

Attenzione: Laura ha gia' provato un modulo e dice che «Gli altri non lo compilano.» Il campo obbligatorio deve stare nello strumento che usano, non in un file a parte.

Nello scenario sono **stime mie**: rimbalzi dal 55% al 25%, un'ora di delega ogni giorno lavorativo. L'autorizzazione "che si vede" non cambia i tempi e non la simulo.
```

## S18 · La decisione

**Consulente** — Quanto ci fa risparmiare?

**DeliR**

```markdown
Sulle stesse 360 richieste:

| | As-Is | To-Be | Differenza |
| --- | --- | --- | --- |
| Attraversamento medio | 1g 15h | 5h 8min | **−87%** |
| Attesa su "Valuta la richiesta di spesa" (richieste sopra soglia) | 3g 2h | 3h 30min | −95% |
| Costo per richiesta | 59,37 € | 33,72 € | **−43%** |

Le due leve fanno cose diverse (stessa simulazione, una leva alla volta):

| Scenario | Attraversamento | Costo per richiesta |
| --- | --- | --- |
| Solo richiesta completa | 2g 18h | 34,46 € |
| Solo delega | 10h 19min | 62,14 € |
| Entrambe | 5h 8min | 33,72 € |

Il **costo** scende con la richiesta completa, che chiedono le fonti. Il **tempo** scende con la delega, che e' **un'ipotesi mia**: da sola, la richiesta completa porta le richieste prima dal responsabile e la coda li' si allunga. La delega va validata con Laura prima di proporla, insieme alla soglia.

Attenzione: il modello non conta l'attesa delle risposte quando si ricostruisce una richiesta (Laura: «Quindi comincia il giro di telefonate.»), quindi entrambi i tempi sono sottostimati.

*Valori simulati, non risultati garantiti: dipendono dalle assunzioni dichiarate nello scenario.*
```

## Da decidere

- **La soglia di autorizzazione** resta una domanda aperta in tutte le scene:
  nessun numero a schermo. La quota di richieste sopra soglia (un terzo) e'
  un parametro incerto: nella scena degli scenari si puo' mostrare che cosa
  cambia facendola variare.
- **S09**: le tre ipotesi del consulente le scrive il consulente nella
  revisione OMG; se preferisci, DeliR puo' proporle lui come domande per il
  workshop.

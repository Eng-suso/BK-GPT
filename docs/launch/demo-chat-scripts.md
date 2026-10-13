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
- Sopra una certa cifra serve l'autorizzazione del responsabile.

**Da chiarire prima del workshop**
- **Divergenza:** chi regolarizza un acquisto urgente. Laura: «So che poi la parte di carta viene messa a posto dopo, ma non so da chi.» Francesca: «La parte di ordine si', la faccio io.»
- **Lacuna:** nessuna fonte dichiara la soglia di autorizzazione. Non la metto nel modello e te la chiedo.
```

## S09 · Confronto con le fonti

**Consulente** — Controlla la bozza contro le interviste. Dimmi cosa non regge.

**DeliR**

```markdown
**10 elementi su 13 hanno una citazione.** Tre no:

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
**Non e' la valutazione: e' l'attesa.**

Francesca: «Se e' fuori, possono essere giorni.» e «Non c'e' un sostituto formale».

Nella simulazione As-Is una richiesta aspetta qui in media **1g 8h**, su un attraversamento di **2g 3h**. E' il collo di bottiglia del processo.

*Valori simulati: volume e costi sono assunzioni del consulente.*
```

## S16 · Ipotesi To-Be

**Consulente** — Cosa cambieresti, partendo da quello che chiedono loro?

**DeliR**

```markdown
Due ipotesi, entrambe da Francesca:

1. **Richiesta completa all'origine.** «Farei in modo che la richiesta nasca gia' completa, con i campi obbligatori.»
2. **Autorizzazione visibile e con un delegato.** «E vorrei che l'autorizzazione fosse una cosa che si vede, non una mail che aspetto.»

Attenzione: Laura ha gia' provato un modulo e dice che «Gli altri non lo compilano.» Il campo obbligatorio deve stare nello strumento che usano, non in un file a parte.

L'effetto sui rimbalzi (dal 55% al 25%) e la finestra giornaliera del delegato sono **assunzioni mie**: le metto nello scenario come tali.
```

## S18 · La decisione

**Consulente** — Quanto ci fa risparmiare?

**DeliR**

```markdown
Sulle stesse 360 richieste:

| | As-Is | To-Be | Differenza |
| --- | --- | --- | --- |
| Attraversamento medio | 2g 3h | 14h 13min | **−72%** |
| Attesa su "Valuta la richiesta di spesa" | 1g 8h | 3h 44min | −88% |
| Costo per richiesta | 65,25 € | 37,97 € | **−42%** |

Il collo di bottiglia si sposta su "Emetti l'ordine di acquisto".

*Valori simulati, non risultati garantiti: dipendono dalle assunzioni dichiarate nello scenario.*
```

## Da decidere

- **La soglia di autorizzazione** resta una domanda aperta in tutte le scene:
  nessun numero a schermo.
- **S09**: le tre ipotesi del consulente le scrive il consulente nella
  revisione OMG; se preferisci, DeliR puo' proporle lui come domande per il
  workshop.

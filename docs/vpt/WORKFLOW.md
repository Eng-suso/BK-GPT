# Engineering workflow del VPT

Regole vincolanti per chiunque lavori sul simulatore e sul Verified Process Twin,
persone o agenti. Obiettivo: il miglior prodotto sul mercato, costruito un punto
del piano alla volta, ognuno verificato prima di passare al successivo.

## I tre file

| File | Cosa contiene | Chi lo aggiorna e quando |
| --- | --- | --- |
| [`PLAN.md`](./PLAN.md) | i punti del piano: meta, comando di misura, dipendenze, stato | chi prende un punto (stato `in corso`) e chi lo chiude (`fatto`) |
| [`HANDOFF.md`](./HANDOFF.md) | **dove siamo adesso**: punto attivo, ultima misura, cosa resta, come riprendere | durante la sessione, a ogni checkpoint, e alla fine. Si riscrive, non si accoda |
| [`LOG.md`](./LOG.md) | la storia: una voce per sessione, la più recente in cima | alla fine di ogni sessione |

Chi arriva legge `HANDOFF.md` per primo: in un minuto deve sapere da dove ripartire.

## Il ciclo di un punto

1. **Inizio sessione**
   - leggi `HANDOFF.md`, poi `PLAN.md`, poi le ultime tre voci di `LOG.md`;
   - controlla i branch aperti rispetto a `main`: rivedi quello che c'è, mergia ciò che è pronto, segnala ciò che non lo è;
   - riallinea il tuo branch a `main`.
2. **Prendi un punto** con stato `da fare` e dipendenze chiuse. Mettilo `in corso`
   in `PLAN.md` e scrivi in `HANDOFF.md` chi lo sta facendo e da quando.
3. **Itera fino alla meta**
   - implementa a piccoli passi, un commit per passo;
   - dopo ogni tentativo lancia il comando di misura del punto;
   - scrivi il numero ottenuto in `HANDOFF.md`;
   - meta non raggiunta: diagnosi, correzione, nuova misura;
   - la meta non si abbassa per chiudere: cambiarla è una decisione di Sohayb, scritta in `LOG.md` con data e motivo.
4. **Checkpoint durante la sessione.** Aggiorna `HANDOFF.md` almeno dopo ogni
   misura, prima di un'operazione lunga e prima di fermarti per qualsiasi motivo.
   Se la sessione si interrompe, il prossimo riparte da lì senza ricostruire nulla.
5. **Verifica del punto**
   - **test:** i test del dominio toccato, più quelli nuovi che dimostrano la meta;
   - **gate UX:** se il punto tocca qualcosa che il cliente vede, vedi sotto;
   - **code review:** skill `code-review` sul diff, poi CodeRabbit sulla PR (sezione sotto).
6. **Chiusura**
   - PR con tanti commit piccoli e la misura finale nel testo;
   - CI verde, poi merge su `main` e push;
   - il branch di lavoro resta allineato a `main`;
   - `PLAN.md` passa a `fatto`, `HANDOFF.md` riscritto per il prossimo, voce in cima a `LOG.md`;
   - poi la sessione si chiude e il prossimo prende il punto successivo.
7. **Bloccato?** Scrivi in `HANDOFF.md` e `LOG.md` cosa blocca e chi lo sblocca,
   metti il punto `bloccato` e passa a un altro.

Commit a nome di Sohayb Raqaq, senza trailer di coautore.

## Skill e code review

- **Skill giuste, ogni volta.** Prima di lavorare carica le skill che `CLAUDE.md`
  indica per quel tipo di lavoro, e solo quelle:

  | Lavoro | Skill |
  | --- | --- |
  | schermata nuova o flusso | `ui-ux-pro-max`, `frontend-developer`, `react-ui-patterns`, `tailwind-design-system` |
  | componente o stato React | `react-ui-patterns`, `react-best-practices`, `react-state-management` (`zustand-store-ts` se tocca uno store) |
  | canvas BPMN | `react-flow-node-ts`, `react-ui-patterns`, `ui-ux-designer` |
  | gate UX e chiusura di un punto con UI | `ui-visual-validator`, `web-design-guidelines`, `accessibility-compliance-accessibility-audit` |
  | grafici e dashboard dei risultati | `dataviz` |
  | backend, simulazione, ricerca | nessuna skill di frontend; per l'API dei modelli `claude-api` |

  Scrivi in `LOG.md` quali skill hai usato.
- **Code review sempre, prima del merge.** Ogni PR passa da due revisioni:
  1. la skill `code-review` sul diff locale prima di aprire la PR, con i rilievi
     corretti o motivati;
  2. la revisione di CodeRabbit sulla PR (configurata in `.coderabbit.yaml`): i suoi
     rilievi si risolvono o si motivano con un commento prima del merge (skill
     `autofix` per applicarli).
  Per cambiamenti a sicurezza, autenticazione o isolamento fra clienti si aggiunge
  `security-review`. Nessun merge con rilievi aperti e senza risposta.

## Regola di prodotto: mangiare la complessità del cliente

Il motore è complesso; il prodotto no. Chi lo usa è un consulente o un'azienda,
spesso con formazione tecnica ma senza il gergo della simulazione e del process
mining. DeliR assorbe la complessità dei dati e degli strumenti del cliente: il
consulente pensa al problema e alla decisione, mai all'interfaccia.

- **Linguaggio di business.** Il percorso ordinario parla di casi, tempi, persone,
  costi, rischi e decisioni. Termini come distribuzione lognormale, seed, gateway,
  ID BPMN, JSON, W1, NGD compaiono solo nei dettagli per specialisti, aperti su
  richiesta, e accanto a una spiegazione in parole semplici.
- **Prima la risposta, poi i dettagli.** Ogni schermata dice cosa abbiamo letto,
  cosa è cambiato e cosa serve decidere. La precisione completa resta disponibile,
  un livello sotto.
- **Il percorso normale è automatico.** Se DeliR può proporre un valore, lo propone
  con la fonte; il consulente approva, modifica o rifiuta.
- **Gli errori dicono cosa fare.** Mai un import parziale silenzioso: si spiega la
  parte non supportata e lo scenario resta com'era.
- **Prova del consulente.** Prima di chiudere un punto con UI, un consulente non
  tecnico deve poter completare il flusso con un file realistico senza decodificare
  nulla. Se servono spiegazioni a voce, il punto non è finito.

## Gate UX: guardare il prodotto

Ogni punto che cambia ciò che il cliente vede si chiude solo dopo averlo guardato
davvero, non solo testato.

1. Cattura gli screenshot del flusso con Playwright (gli e2e in `e2e/` simulano il
   backend, quindi basta il frontend): desktop 1440 × 900 e mobile (Pixel 7).
2. **Apri ogni immagine e leggila**, testo compreso. Controlla:
   - le parole che il cliente legge: niente gergo nel percorso ordinario;
   - la gerarchia: la risposta e l'azione principale si vedono per prime;
   - testo tagliato, sovrapposizioni, scroll orizzontale, stati vuoti ed errori;
   - focus visibile e navigazione da tastiera (axe, già usato negli e2e);
   - che sembri un prodotto enterprise, non una demo.
3. Salva le immagini in `docs/vpt/ux/<punto>/` (prima e dopo, se è un cambiamento)
   e scrivi in `LOG.md` cosa hai controllato e cosa hai corretto.
4. Se una schermata non passa, il punto torna al passo 3 del ciclo.

Le skill locali per questo lavoro sono elencate in `CLAUDE.md` (UI/UX, accessibilità,
visual QA).

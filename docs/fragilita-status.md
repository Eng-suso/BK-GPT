# Fragilità del prodotto — stato dei lavori

Documento vivo. L'analisi che lo ha prodotto sta in
[`fragilita-audit.md`](fragilita-audit.md) e non si tocca: è la fotografia del
24 settembre 2026. Qui c'è cosa è stato chiuso, cosa manca, e qual è il
prossimo passo.

**A chi serve:** a più sessioni agente in parallelo, e a Sohayb per sapere dove
siamo senza rileggere i diff.

**Come si usa.** Chi prende in mano il lavoro legge §② e fa quello. Chi lo posa
aggiorna §① (la riga del difetto che ha chiuso), §② (il prossimo passo, uno
solo) e §⑤ (la riga di log). Un difetto non si dichiara chiuso se i suoi test
non sono verdi: §① distingue *scritto* da *verificato*, ed è la distinzione che
vale.

**Regole di ingaggio** (§③) prima di toccare qualcosa: ci sono difetti che non
si chiudono senza una decisione di Sohayb, e provarci produce lavoro da buttare.

Ultimo aggiornamento: 2026-09-24.
Branch di lavoro: `fix/fragilita-audit`.

---

## ① Stato

Stati possibili: **da fare** · **in corso** (con branch) · **scritto** (codice
fatto, test non ancora verdi) · **fatto, verificato** · **bloccato** (serve una
decisione, §④).

### Backend

| ID | Difetto | Gravità | Stato |
| --- | --- | --- | --- |
| B1 | Il tenant arriva da un header, non dalla credenziale | Bloccante | **bloccato** — §④.1 |
| B2 | Autenticazione spenta di default, CORS `*`, tutti admin | Bloccante | da fare |
| B3 | Memoria di un consulente solo (`default_consultant_id`, 20 punti) | Bloccante | **bloccato** — §④.2 |
| B4 | Architettura mono-processo non dichiarata né difesa | Alto | da fare |
| B5 | 73 handler su 76 sono `def` sync: threadpool a 40 posti | Alto | da fare |
| B6 | `_TRACE_EVENTS` mai potato: leak di memoria certo | Alto | da fare |
| B7 | La risposta si perde se il client cade a metà stream | Bloccante | da fare |
| B8 | Run di simulazione `pending` per sempre dopo un crash | Alto | da fare |
| B9 | `str(exc)` verso il client in 20 punti | Medio | da fare |
| B10 | Spesa LLM senza tetto | Alto | **bloccato** — §④.3 |
| B11 | La traccia di osservabilità non è legata al tenant | Medio | da fare |
| B12 | Liste senza `LIMIT` né paginazione | Medio | da fare |

### UI

| ID | Difetto | Gravità | Stato |
| --- | --- | --- | --- |
| U1 | Nessun ErrorBoundary: un throw è schermo bianco | Bloccante | da fare |
| U2 | Zero code splitting: `bpmn-js` e `recharts` nel bundle iniziale | Medio | da fare |
| U3 | La Simulazione mostra `0` al posto di «nessun dato» | Bloccante | da fare |
| U4 | 110 stringhe italiane scritte nel codice, fuori da i18next | Alto | da fare |
| U5 | Accessibilità verificata con axe su una pagina sola | Alto | da fare |
| U6 | L'errore del backend si legge in interfaccia come sta | Medio | da fare |
| U7 | PWA dichiarata, PWA assente | Medio | **bloccato** — §④.4 |

### UX

| ID | Difetto | Gravità | Stato |
| --- | --- | --- | --- |
| X1 | «Cronologia eliminata» senza conferma né annulla | Alto | da fare |
| X2 | Clienti è un elenco che non si apre | Alto | **bloccato** — §④.5 |
| X3 | URL sbagliato, rimando muto a `/projects` | Medio | da fare |
| X4 | La ricerca globale cerca il cliente per nome, non per id | Medio | da fare |
| X5 | Nessun tetto alle simulazioni concorrenti | Medio | da fare |

### Verifica

| ID | Difetto | Gravità | Stato |
| --- | --- | --- | --- |
| V1 | La suite `e2e/` non attraversa il backend: tutto mockato | Bloccante | da fare |
| V2 | Visual regression e Lighthouse opt-in, non bloccano il merge | Medio | da fare |

---

## ② Prossimo passo

**Uno solo.** Chi prende il lavoro fa questo, poi riscrive questa sezione.

> **Ondata 1 — backend, nessuna decisione di prodotto richiesta.**
> Nell'ordine: B6 (potatura tracce), B11 (traccia per tenant), B8 (scadenza dei
> run `pending`), B9 + U6 (errore che non espone l'eccezione), B2 (l'ambiente
> non si avvia in silenzio senza autenticazione), B4 (più di un worker si
> rifiuta invece di corrompere i checkpoint).
>
> Ogni difetto è un commit. Nessuno di questi tocca il frontend.

---

## ③ Regole di ingaggio

1. **Un difetto, un commit.** Il messaggio dice cosa smette di succedere, non
   quale file è cambiato. Italiano, a nome di Sohayb Raqaq, nessun trailer di
   co-autore.
2. **Un difetto non è chiuso senza un test che lo riproduce.** Il test va
   scritto prima del fix e deve fallire prima e passare dopo. Se il difetto non
   è riproducibile in test (B4, B5), lo dice §① nella riga.
3. **Non allargare.** L'audit ha 26 righe; non se ne aggiungono altre qui senza
   passare da §⑤. Un difetto nuovo trovato strada facendo va in
   [`bugs.md`](bugs.md), non in questo file.
4. **Frontend: si usano le skill del routing** in `CLAUDE.md`, le più piccole
   che servono. Per U1/U3: `react-ui-patterns`, `frontend-dev-guidelines`. Per
   U5: `accessibility-compliance-accessibility-audit`, `wcag-audit-patterns`.
   Per U2: `react-best-practices`.
5. **I bloccati non si toccano.** Prima la decisione in §④, poi il codice.
   Scrivere B1 o B3 senza la decisione significa riscriverli dopo.
6. **Chi posa il lavoro aggiorna §①, §② e §⑤ nello stesso commit del fix.** Un
   documento vivo aggiornato in un commit a parte è un documento morto.

---

## ④ Cosa serve da Sohayb

Cinque decisioni. Finché non arrivano, i difetti che dipendono da loro restano
**bloccati** in §①, e questo è corretto: non sono dimenticanze.

1. **B1 — a cosa si lega lo spazio di lavoro.** Oggi è un header e il token sta
   nel browser. Le strade sono due: (a) un token per spazio di lavoro, con la
   mappa token → tenant lato server, che si fa subito e regge un pilota singolo;
   (b) Track B con Supabase Auth, identità per persona, che è la strada vera e
   costa settimane. Se la risposta è (b), B1 e B3 si chiudono insieme e questa
   ondata non esiste.
2. **B3 — quando muore `default_consultant_id`.** È lo stesso bivio di B1: la
   memoria per consulente ha senso solo se esiste il consulente. Vedi
   [`deployment-and-tenancy.md`](deployment-and-tenancy.md), Track B.
3. **B10 — chi paga e quanto.** Il gateway registra la spesa e non la ferma. Il
   tetto è P0.4 in [`llm-spend-status.md`](llm-spend-status.md): serve una chiave
   per ambiente e un limite mensile deciso da te, non dal codice.
4. **U7 — la PWA serve davvero?** Il prodotto si chiama PWA e non ha né manifest
   né service worker. O si smette di chiamarla così, o si decide cosa deve
   funzionare offline. La seconda costa; la prima è una riga di documentazione.
5. **X2 — cos'è la schermata di un cliente.** La rotta esiste nel codice e non è
   montata. Serve sapere cosa ci si legge: progetti, storico, memoria del
   cliente, fatturato. Senza, si costruisce un contenitore vuoto.

---

## ⑤ Log

Una riga per passo chiuso. Chi la scrive mette data, ID del difetto e come si
verifica.

| Data | ID | Cosa è cambiato | Verifica |
| --- | --- | --- | --- |
| 2026-09-24 | — | Audit end-to-end del prodotto: 26 difetti fra backend, UI, UX e verifica. Aperto questo documento e il branch `fix/fragilita-audit`. | [`fragilita-audit.md`](fragilita-audit.md) |

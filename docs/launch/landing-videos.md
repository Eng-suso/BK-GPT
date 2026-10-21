# DeliR — video della landing (Problem → Agitate → Solve)

Sei video brevi e un percorso completo per delir.it, tutti dalle stesse
registrazioni del prodotto. Niente scene illustrate: ogni fotogramma è
un'interfaccia di DeliR sul caso dimostrativo.

    npm run media:landing          # cattura + montaggio
    npm run media:landing:render   # solo montaggio

Cattura: `e2e/launch-media/landing-videos.spec.ts`. Copione (targhette IT/EN,
capitoli, tagli): `e2e/launch-media/landing-videos.json`. Montaggio:
`scripts/landing_videos_edit.py`. Uscita in `artifacts/landing-videos/`
(non versionato): `video/` master, `web/` MP4 + WebM + poster + VTT IT/EN.

## Regole di regia

| Regola | Come è applicata |
| --- | --- |
| Prodotto sempre per intero | Il fotogramma della UI è ridotto all'86% dentro una cornice; nessun ritaglio |
| Lento | Velocità reale (mai accelerato), cursore a 1,3 s per movimento, pause di lettura 2–3 s |
| Targhette IT + EN | Sotto il prodotto, mai sopra la UI; cambiano con i `tag(rec, …)` registrati in cattura |
| Pochi zoom | Uno solo, ×1,3, mentre si scrive nella chat |
| Niente bpmn.io | Il watermark del disegno è nascosto solo durante la cattura |
| Processo semplice | `data/simple.bpmn`: BPMN 2.0.2, 2 corsie, 5 attività, split e merge esclusivi espliciti, eventi con nome |
| Simulazione | Processo intero + 6 KPI in movimento (coda, tempo di attraversamento, concluse, throughput, costo, occupazione) |
| Solo il prodotto | Problem e Agitate sono schermate di DeliR (interviste grezze, domanda bloccante, chi fa cosa, heatmap) |

## Tagli

| Video | Durata | Scene |
| --- | --- | --- |
| 01 Problem | ~35 s | Fonti → testo grezzo delle interviste |
| 02 Agitate | ~35 s | Domanda bloccante sulla soglia → "non lo so" fra le fonti → attesa misurata |
| 03 Process Discovery | 30–45 s | Affermazioni con citazione → chat con DeliR → domanda aperta |
| 04 Evidence & BPMN | 35–50 s | As-Is BPMN → evidenze 100% → citazioni per elemento → versioni |
| 05 Analysis & Simulation | 40–60 s | Replay As-Is → heatmap → replay To-Be |
| 06 Results & Deliverables | 25–40 s | Confronto As-Is/To-Be → consegna → cruscotto del process owner |
| Walkthrough | 3–5 min | Tutte le scene del prodotto per intero |

## Loop di iterazione

Ogni modifica: cattura della scena (`-g lv-<scena>`), montaggio del taglio,
estrazione di fotogrammi a istanti fissi e revisione (inquadratura intera,
targhetta coerente con l'azione, nulla di tagliato, KPI tutti visibili). Lo
screencast manda fotogrammi solo quando la pagina cambia: si campiona per
tempo (`scene.json`), non per indice.

## Dati

Il processo semplice usa i run Prosimos dell'hero (`data/hero-runs.json`, stessi
id degli elementi) con i nomi in italiano (`simpleData.ts`). Le citazioni delle
evidenze sono alla lettera dal golden set: `claimQuote` si ferma se una manca.
Azienda e persone sono fittizie; i valori della simulazione sono simulati.

## Licenza bpmn-js

Il watermark bpmn.io resta nel prodotto: la licenza di bpmn-js chiede che
resti visibile nell'applicazione. Nei video è nascosto su richiesta; da
verificare con chi gestisce le licenze prima della pubblicazione.

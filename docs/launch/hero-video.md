# DeliR — video hero della landing

Loop muto di **10 s** nell'hero della landing, accanto a headline e
subheadline. Non spiega: fa pensare "aspetta, fa tutto questo?" nei primi 5
secondi. Ogni fotogramma chiave (2 s, 4 s, 7 s) regge da solo.

Generazione: `npm run media:hero` (cattura delle 5 inquadrature + montaggio);
uscita in `landing/media/` (WebM, MP4, poster).

## Schermate reali usate

| Momento | Schermata del prodotto | Dati |
| --- | --- | --- |
| Conoscenza sparsa | Progetto → scheda **Sources** (lista fonti con affermazioni) | 4 fonti del caso demo |
| As-Is verificato | Editor del processo: canvas BPMN + pannello **Evidence** (copertura 100%, citazioni) | As-Is v3, 6 corsie |
| Cosa cambiare | Simulazione → **Heatmap** sull'attesa, scheda del collo di bottiglia | run As-Is (Prosimos) |
| Testa prima | Simulazione → **Scenario workspace** (SIM-14): AS-IS, A, B con intervallo al 95% e verdetto | 9 run Prosimos, seed comune |
| Continua a migliorare | Canvas con lo scenario B sul processo (task modificati, legenda) + inspector "In scenarios" | patch dello scenario B |

Interfaccia in inglese (la landing e' in inglese): i nomi del processo demo
sono tradotti solo per la cattura (`e2e/launch-media/heroLocale.ts`).

## Storyboard

| Tempo | Inquadratura | Movimento | Testo |
| --- | --- | --- | --- |
| 0,0–2,0 | Quattro file (procedura PDF, trascrizione, foglio Excel, verbale) sparsi sopra la scheda Sources | Convergono ciascuno sulla sua riga; le righe reali compaiono con il numero di affermazioni | Scattered knowledge |
| 2,0–4,0 | Canvas dell'As-Is | Il processo si compone da sinistra a destra (corsie, task, gateway), poi entra il pannello Evidence con la copertura | Verified As-Is |
| 4,0–5,5 | Heatmap sullo stesso processo | La camera va su "Autorizza spesa" (rosso) e sulla scheda del collo di bottiglia | Find what needs to change |
| 5,5–8,0 | Scenario workspace | AS-IS, A, B entrano riga per riga; B si accende: "Better" su tempo e costo, A "Not certain" sul costo | Test before you recommend |
| 8,0–10,0 | Scenario B sul processo + inspector | I task cambiati si evidenziano, l'inspector dice cosa cambia; dissolvenza sul primo fotogramma | Keep improving |

Transizioni: dissolvenza incrociata breve (0,35 s), camera con easing, niente
zoom drammatici. L'ultimo 0,4 s sfuma nel fotogramma 0: il loop non ha stacco.

## Onesta' dei numeri

I valori degli scenari escono da 18 simulazioni Prosimos vere
(`scripts/launch_media_scenarios.py`, 6 ripetizioni per scenario, seed
consecutivi). Il verdetto lo calcola il workspace (intervallo al 95%, prove
appaiate): B e' migliore su tempo e costo; A solo sul tempo, sul costo resta
"Not certain". Lo dice il prodotto, non la sceneggiatura. Tutto resta "simulated
example" su dati dimostrativi; in basso a destra resta il disclaimer.

## Consegna web

- WebM VP9 (principale) + MP4 H.264 (Safari/fallback), 1600×900, senza audio.
- Poster WebP + JPG dal fotogramma del workspace (il momento piu' forte).
- `autoplay muted loop playsinline`, `preload="metadata"` + poster in
  preload: la pagina mostra subito il poster, il video parte appena pronto.
- `prefers-reduced-motion`: niente autoplay, resta il poster.
- Fuori schermo il video si mette in pausa (IntersectionObserver).

## Risultato

| File | Peso |
| --- | --- |
| `landing/media/delir-hero.webm` (VP9, 1600×900, 10,2 s) | ~1,0 MB |
| `landing/media/delir-hero.mp4` (H.264 fallback) | ~1,1 MB |
| `landing/media/delir-hero.webp` (poster, momento del workspace) | ~60 KB |
| `landing/fonts/geist-latin-wght-normal.woff2` | 29 KB |

La landing (`landing/index.html`) e' statica: `python3 -m http.server -d
landing`. `e2e/launch-media/landing.spec.ts` verifica autoplay, loop senza
pause, riduci movimento e assenza di scorrimento orizzontale a 390 px.

## Revisione critica (conversione)

- **Forte**: al secondo 7 il workspace con tre scenari, intervalli e "Better"
  dice da solo cosa fa DeliR; e' anche il poster, quindi chi non vede il video
  legge comunque la promessa.
- **Forte**: nessuna UI inventata; tutte le schermate sono del prodotto a main
  (PR #116), i numeri sono simulati davvero.
- **Debole**: a 390 px il testo dell'interfaccia non si legge (restano le chip e
  le forme). Una variante verticale ritagliata sulle inquadrature della camera
  sarebbe il prossimo passo per il mobile.
- **Debole**: lo stato del progetto ("In corso") resta italiano nell'interfaccia
  inglese: gli stati sono valori canonici non tradotti (lacuna di i18n del
  prodotto, non del video).
- **Da decidere**: il video va accanto alla headline; se la headline si accorcia,
  conviene metterlo sotto, a tutta larghezza (1200 px), per leggere meglio la UI.

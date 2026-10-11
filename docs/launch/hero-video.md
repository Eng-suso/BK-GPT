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
| 5,5–8,0 | Scenario workspace | AS-IS, A, B entrano riga per riga; B si accende come "Better", A resta "Unclear" (l'intervallo include lo zero) | Test before you recommend |
| 8,0–10,0 | Scenario B sul processo + inspector | I task cambiati si evidenziano, l'inspector dice cosa cambia; dissolvenza sul primo fotogramma | Keep improving |

Transizioni: dissolvenza incrociata breve (0,35 s), camera con easing, niente
zoom drammatici. L'ultimo 0,4 s sfuma nel fotogramma 0: il loop non ha stacco.

## Onesta' dei numeri

I valori degli scenari escono da 9 simulazioni Prosimos vere
(`scripts/launch_media_scenarios.py`, 3 ripetizioni per scenario, seed
consecutivi). A non e' dichiarato migliore perche' il suo intervallo include
lo zero: lo dice il prodotto, non la sceneggiatura. Tutto resta "simulated
example" su dati dimostrativi; in basso a destra resta il disclaimer.

## Consegna web

- WebM VP9 (principale) + MP4 H.264 (Safari/fallback), 1600×900, senza audio.
- Poster WebP + JPG dal fotogramma del workspace (il momento piu' forte).
- `autoplay muted loop playsinline`, `preload="metadata"` + poster in
  preload: la pagina mostra subito il poster, il video parte appena pronto.
- `prefers-reduced-motion`: niente autoplay, resta il poster.
- Fuori schermo il video si mette in pausa (IntersectionObserver).

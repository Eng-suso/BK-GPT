# Piano video prodotto: verifica contro delir-landing

Verifica del documento "DeliR · Piano video prodotto (handoff)" contro il
codice di `eng-suso/delir-landing` (branch `main`, 12 ottobre 2026). Qui stanno
solo i punti in cui il piano e il sito non coincidono, e cosa decidere prima
di registrare.

## Confermato nel codice

| Affermazione del piano | Dove |
| --- | --- |
| 17 clip 1920×1080, da 5,3 a 32,5 s | `public/product-clips/*.mp4`, `src/lib/productClips.ts` |
| Solo 6 clip hanno un'inquadratura telefono | `mobileFocus` in `src/components/ProductFilm.tsx` |
| Frasi dell'hero a 0/4/8/12 s su un loop di 16 s | `narration` in `src/components/Hero.tsx` |
| VTT con un solo cue su tutta la durata | `public/product-clips/*.vtt` |
| Nessun `Cache-Control` per `/product-clips/` | `public/_headers` copre solo `/assets/*` |
| mp4 prima del webm, caricamento al 20% di visibilita' | `ProductFilm.tsx` |

## Contraddizioni da chiudere prima di girare

| # | Il piano dice | Il sito oggi | Conseguenza | Proposta |
| --- | --- | --- | --- | --- |
| 1 | Hero di 20 s, frasi a 0/5/10/15 s, "il copy non si tocca" | Le frasi partono a 0/4/8/12 s, scritte in `Hero.tsx`; `duration: 16` in `productClips.ts` | Un hero da 20 s con gli stessi file sfasa le frasi: serve una modifica al codice della landing | Hero da 16 s (4 × 4 s), oppure il team landing cambia i tempi in `Hero.tsx` |
| 2 | Si consegnano file "con gli stessi nomi" | Le 17 clip hanno id fissi in `productClips.ts`; S01, S02, S04, S19–S23 non hanno una clip corrispondente | Le scene nuove (Home, consulente, intervista dal vivo, consegna, ricerca) non entrano nel sito senza nuovi id | Lista di mappatura scena → id; i nuovi id li aggiunge il team landing |
| 3 | Tab 01 Evidenze ... 05 Scenari | In `Journey.tsx` gli id sono `product-03, 02, 01, 04, 05` e `chapterClips` raggruppa le clip in un altro ordine (non usato dalla pagina) | Rischio di consegnare clip al tab sbagliato | Usare `benefits` in `Journey.tsx` come unica fonte della mappatura |
| 4 | Varianti 4:5 con `-4x5` | `width: 1920, height: 1080` fissi in `clip()`, l'aspect ratio del riquadro viene dalla clip | Senza modifica a `ProductFilm.tsx` il 4:5 viene mostrato in un riquadro 16:9 | Il team landing aggiunge sorgente e poster per breakpoint prima della consegna |
| 5 | "Se l'mp4 non si legge il webm non viene mai provato" | `onError` e' sul `<video>`; l'errore di un `<source>` non risale al `<video>` | Il difetto va riprodotto prima di segnalarlo | Test in Playwright con un mp4 rotto prima di aprire la segnalazione |

## Tagli della durata

Le 23 scene sommano circa 3'42" a 1×. Per tab, con le durate del piano:

| Tab | Scene | Durata a 1× |
| --- | --- | --- |
| 01 Evidenze | S04, S05, S08, S09 | 39 s |
| 02 Lacune | S06, S07 | 24 s |
| 03 Contesto | S01, S02, S03, S23 | 36 s |
| 04 Decisioni | S10, S11, S16, S19–S22 | 60 s |
| 05 Scenari | S12–S15, S17, S18 | 63 s |

Il piano chiede clip da 20–30 s: Evidenze, Contesto, Decisioni e Scenari
superano il limite. O si consegnano piu' clip per tab (il sito lo supporta,
con i pulsanti 01…n), o si tagliano scene. Da decidere con Sohayb prima del
montaggio.

## Hero: cosa arriva al team landing

L'hero: 25 s in loop, cinque momenti da 5 s (fonti, evidenze, simulazione
As-Is, To-Be misurato contro l'As-Is, invio). Il To-Be e' entrato il 14
ottobre: senza, la simulazione non diceva quanto migliora. Si genera con
`npx playwright test -c playwright.launch.config.ts heroLoop` e
`python3 scripts/launch_media_montage.py hero`.

| File | Formato | Lingua |
| --- | --- | --- |
| `hero-loop.{mp4,webm,jpg,webp}` | 16:9, 1920×1080 | italiano (stesso nome di oggi) |
| `hero-loop.en.{mp4,webm,jpg,webp}` | 16:9, 1920×1080 | inglese |
| `hero-loop-4x5.{mp4,webm,jpg,webp}` | 4:5, 1080×1350 | italiano |
| `hero-loop-4x5.en.{mp4,webm,jpg,webp}` | 4:5, 1080×1350 | inglese |

Il nome inglese segue la convenzione dei VTT (`<id>.<lingua>`). Modifiche
richieste al sito, tutte nel codice e nessuna nel copy:

- `Hero.tsx`: cinque frasi a 0/5/10/15/20 s, in entrambe le lingue; la quarta
  e' nuova (il To-Be: -87% di attraversamento, -43% di costo per caso) e va
  scritta dal team landing;
- `productClips.ts`: `duration: 25` per `hero`;
- `ProductFilm.tsx`: la sorgente per lingua (`hero-loop.en.mp4` quando la
  lingua e' l'inglese) e la variante 4:5 sotto i 768 px.

Come sono fatti:

- velocita' 1×, cursore da 1,2 s, nessuna accelerazione;
- il 4:5 e' un ritaglio della stessa ripresa desktop, con gli zoom: si vede
  sempre il prodotto da desktop (decisione del 14 ottobre, la ripresa da
  telefono non si capiva). Il prezzo e' un testo piu' piccolo: minimo 8 px a
  350 px invece di 11;
- ogni momento ha la sua targhetta blu (#004580) in alto a sinistra, numerata,
  che dice cosa succede, in italiano e in inglese;
- l'apertura parte da interviste, Word, Excel e l'export del gestionale; le
  evidenze collegano con una linea blu la citazione all'attivita'; la
  simulazione mostra il processo e quattro KPI in movimento;
- `scripts/launch_media_montage.py` si ferma se un testo inquadrato scende
  sotto il minimo alla dimensione del sito (11 px a 756 px per il 16:9, il
  tablet; 8 px a 350 px per il 4:5), se un colpo d'insieme dura piu' di 2 s o se il logo
  bpmn.io entra in quadro;
- la dicitura "Caso dimostrativo · valori simulati" ("Demo case · simulated
  values") e' dentro il video, nella fascia in basso che la camera lascia
  libera.

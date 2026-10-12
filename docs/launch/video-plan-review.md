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

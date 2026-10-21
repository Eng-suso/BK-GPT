# DeliR — video della landing sul caso semplice

I video del sito (hero e un video per beneficio) raccontano **un solo caso,
end-to-end**: una richiesta di acquisto in un'azienda fittizia. Il processo è
volutamente piccolo (tre corsie, cinque attività, una decisione con
rilavorazione) perché si legga in un colpo d'occhio anche a 720 px.

Il video lungo di presentazione (`video-storyboard.md`, caso acquisti
indiretti) resta com'è: altro pubblico, altra durata.

## Il caso

| Cosa | Dove |
| --- | --- |
| Disegno (IT/EN, stessi id) e simulazioni Prosimos | `scripts/launch_media_simple_case.py` → `e2e/launch-media/data/simple/` |
| Fonti, citazioni, divergenze, domanda aperta, review, consegna | `e2e/launch-media/simple/case.ts` |
| Backend demo per le riprese | `e2e/launch-media/simple/mockApi.ts` |
| Riprese | `e2e/launch-media/simple/clips.spec.ts` |
| Tagli (camera, dissolvenze, loop, export web) | `storyboard.json` → `cuts.simple-*` + `scripts/launch_media_edit.py` |

La storia si regge su ciò che le fonti dicono:

1. **Le versioni che non tornano.** La procedura: «Il responsabile autorizza la
   spesa entro un giorno lavorativo». Francesca: «Laura firma il martedì e il
   giovedì, quando è in sede».
2. **La lacuna che DeliR non riempie.** La soglia di firma non la dichiara
   nessuno (la procedura rimanda a una tabella che non c'è): resta una domanda.
3. **Il To-Be l'hanno chiesto loro.** Campi obbligatori (Francesca, Paolo) e un
   delegato che firma quando Laura non c'è (Francesca).

Numeri (Prosimos 2.1.0, seed 20261021, 300 richieste, 5 al giorno per
assunzione del consulente): As-Is **2,28 giorni** → To-Be **0,89 giorni**
(−61%), costo per richiesta **53 € → 30 €**; collo di bottiglia **Autorizza la
spesa** (attesa media 1g 11h). Volume, persone e costi orari sono assunzioni
del consulente, dichiarate nella provenienza dei parametri.

## Regole dei video della landing

- **Leggibili a 720 px.** Riprese a 1280×720 con densità 1,5 (fotogrammi
  1920×1080, testi un terzo più grandi) e un'inquadratura stretta (`rec.focus`,
  zoom 1,5–2,2) per ogni momento di lettura. Una UI registrata a 1920 px e
  mostrata a 720 px resta al 37%: i testi diventano illeggibili.
- **Il processo è il protagonista.** Nelle scene di simulazione la tela ha il
  processo grande e solo due grafici compatti; la camera inquadra il diagramma.
- **Niente testo bruciato nel video.** Sulla landing il testo sta accanto alla
  clip; nel video solo il disclaimer «Azienda, persone e valori dimostrativi ·
  simulazione».
- **Loop senza stacco.** Gli ultimi 0,6 s sfumano nel primo fotogramma.
- **Due lingue, interfaccia compresa.** Stessa sceneggiatura, UI e dati in IT o EN.
- **Link del cliente con l'indirizzo di produzione** (`DELIR_SHARE_ORIGIN`,
  default `https://app.delir.it`), non quello locale della ripresa.
- **Marchio del renderer BPMN fuori dalle riprese** (solo nelle registrazioni;
  `DELIR_SHOW_BPMN_WATERMARK=1` lo lascia). Il prodotto non cambia. Da
  verificare con la licenza bpmn.io prima della pubblicazione.

## Tagli

| Taglio | Riprese | Durata |
| --- | --- | --- |
| `hero` | fonti → As-Is → evidenza → replay As-Is → scenari → link al cliente | 23,6 s |
| `evidenze` | fonti con citazioni verificate → pannello evidenze del disegno | ~21 s |
| `lacune` | divergenza procedura/intervista → domanda aperta sulla soglia | ~21 s |
| `contesto` | chat: DeliR ricostruisce l'As-Is → panoramica del progetto | ~18 s |
| `decisioni` | review con DeliR su «Autorizza la spesa» → consegna e link | ~27 s |
| `scenari` | replay As-Is → heatmap → workspace scenari e decision record | ~27 s |

Export: MP4 H.264 1600×900 (CRF 25) e poster JPG/WebP in
`artifacts/launch-media/landing-v3/<taglio>.<lingua>.*`.

## Rigenerare

```bash
# 1. Dati (solo se cambia il caso): runner Prosimos su :5000 (ops/prosimos/runner)
PYTHONPATH=. WORKSPACE_DATABASE_URL=postgresql+psycopg://x:x@127.0.0.1:1/x \
  uv run python scripts/launch_media_simple_case.py
# 2. Riprese (IT ed EN) e disclaimer
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/percorso/chrome npx playwright test -c playwright.launch.config.ts simple/clips
# 3. Montaggio
python3 scripts/launch_media_edit.py simple-hero-it simple-evidenze-it simple-lacune-it \
  simple-contesto-it simple-decisioni-it simple-scenari-it simple-hero-en simple-evidenze-en \
  simple-lacune-en simple-contesto-en simple-decisioni-en simple-scenari-en
```

`WORKSPACE_DATABASE_URL` serve solo perché alcuni moduli del backend creano
l'engine all'import: lo script non si collega al database.

Se cambiano i tempi delle riprese, i tagli dell'hero usano `from`/`keep` fissi:
ricontrollare `scene.json` (`camera`, `marks`) e le frasi sincronizzate
nell'hero della landing (`Hero.tsx`, 0 / 4,7 / 9,2 / 13,8 / 18,4 s).

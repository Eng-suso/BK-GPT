# DESIGN.md — riferimenti esterni di stile

Ispezione del 2026-10-19 con REA (`capture_browser_scenario`, Chrome 141 headless,
viewport 1440×900, `it-IT`). REA ha registrato il traffico di rete e gli screenshot;
CSS e HTML sono stati poi scaricati e contati con uno script (frequenze = numero
di dichiarazioni nel CSS, non pixel a schermo).

Si copia **solo lo stile**: valori di tipografia, colore, raggi, ombre, movimento.
Mai loghi, foto, file font, marchi o testi. SF Pro, Graphik e Roobert non hanno
licenza per DeliR: si usano solo pesi, dimensioni e tracking su font nostri.

Questo documento è un riferimento. La fonte di verità resta
[satin-design-system.md](satin-design-system.md) con i token in
`frontend/styles/tokens/`.

| Sito | Pagina | CSS letti | Dichiarazioni | Font caricati |
| --- | --- | --- | --- | --- |
| Apple | apple.com/it/iphone-duo | 10 file esterni, 1,88 MB | 23.963 | 10 woff2 SF Pro Text/Display/Icons |
| Miro | miro.com | 2 esterni + 9 `<style>` inline (Framer) | 14.417 | Roobert PRO, Inter, Noto Sans, Open Sans |
| Lucidchart | lucidchart.com/pages | 6 `<style>` inline (DOM via REA; curl bloccato) | 8.320 | 9 woff2 Graphik / GraphikWide |
| ChatGPT | chatgpt.com (non loggato, tema scuro) | 2 CSS StyleX, 0,52 MB | 8.859 | nessun file font: stack di sistema |

---

## 1. Apple

### Font e pesi
- Famiglie: **SF Pro Text** 1.824 dichiarazioni (58%), **SF Pro Display** 1.281 (41%).
  Regola: Text sotto ~20px, Display da 20px in su. Fallback: Helvetica Neue, Helvetica, Arial.
- Pesi: **600 ×222**, **400 ×156**, 500 ×5, 700 ×3. In pratica due soli pesi.
  Niente bold 700: i titoli sono semibold.

### Scala tipografica (combinazioni reali nella stessa regola)
| Size | Line-height | Tracking | Peso | Occorrenze | Uso |
| --- | --- | --- | --- | --- | --- |
| 12px | 1.333 | -0.01em | 400/600 | 52 | note, legali |
| 14px | 1.286 | -0.016em | 400/600 | 62 | UI secondaria, nav |
| 14px | 1.429 | -0.016em | 400 | 10 | testo corrente piccolo |
| **17px** | 1.235 / 1.471 | **-0.022em** | 400/600 | 73 | corpo base, controlli |
| 19px | 1.21 / 1.42 | +0.012em | 400/600 | 24 | lead |
| 21px | 1.19 | +0.011em | 600 | 26 | titoletti |
| 24px | 1.167 | +0.009em | 600 | 20 | titolo card |
| 28px | 1.143 | +0.007em | 600 | 17 | titolo sezione |
| 32px | 1.125 | +0.004em | 600 | 9 | |
| 40px | 1.1 | 0 | 600 | 7 | |
| 48px | 1.083 | -0.003em | 600 | 7 | headline |
| 64px | 1.063 | -0.009em | 600 | 5 | hero (solo marketing) |

Frequenza font-size: 17px ×84, 14px ×72, 12px ×67, 21px ×30, 19px ×28, 28px ×25, 24px ×22.
Il tracking è **ottico**: negativo sui corpi piccoli (-0.022em a 17px), leggermente positivo
fra 19 e 32px, di nuovo negativo sopra i 48px. `0em` compare 984 volte (reset).

### Colori (le più frequenti in assoluto, 1.525 occorrenze)
| Ruolo | Valore | Occorrenze |
| --- | --- | --- |
| Testo primario | `#1d1d1f` / rgb(29,29,31) | 94+ |
| Testo secondario | `#6e6e73` | 87 |
| Testo terziario | `#86868b` | 55 |
| Sfondo chiaro alternato | `#f5f5f7` | 138 |
| Bianco | `#ffffff` | 227 |
| Accento (pulsante) | `#0071e3` | 57 |
| Accento hover / active | `#0076df` / `#006edb` | token `--sk-button-*` |
| Link | `#0066cc` (chiaro), `#2997ff` (scuro) | 4 / 9 |
| Velature | `rgba(0,0,0,.48/.56/.64)`, `rgba(255,255,255,.8)` | 39–53 ciascuna |
| Separatori | `#d2d2d7`, `#e8e8ed` | |

Palette = grigi neutri caldi + **un solo blu**. Le gerarchie si fanno con tre grigi e con
velature di nero/bianco, non con colori diversi.

### Raggi
`50%` ×23, `999px`/`980px` (capsula, pulsanti) ×18, 28px ×8 (card grandi), 22px ×4,
8–10px ×8 (controlli piccoli), 5–6px (badge). Pulsante: capsula 980px, padding 9×16 (piccolo)
o 12×22 (grande), min-width 60–70px.

### Ombre
Quasi assenti: 31 dichiarazioni in 1,9 MB di CSS. Le più usate sono **anelli di focus**:
`0 0 0 3px #000, 0 0 0 5px #0071e3` ×6, `0 0 0 3px #fff` ×4. Profondità ottenuta con
colore di sfondo (`#f5f5f7` su bianco) e **vetro**: `backdrop-filter: blur(20px)` ×10
(nav, barra di acquisto, controlli sopra le immagini), sfondo `rgba(255,255,255,.8)`.

### Movimento
- Easing: **`cubic-bezier(0.4,0,0.6,1)` ×268** (curva standard Apple), `ease-in-out` ×100,
  `cubic-bezier(0,0,0.2,1)` ×95 (entrata), `ease-out` ×95, `ease` ×83, `linear` ×76,
  `cubic-bezier(.25,.1,.3,1)` ×13. Molle rare: `cubic-bezier(0.4,0,0.3,2)` ×5.
- Durate: **240ms** (.24s + 240ms) ×98, **250ms** ×64, 400ms ×53, 80ms ×52, 500ms ×49,
  300ms ×36, 320ms ×26, 100ms ×27, 200ms ×22.
- Schema tipico: `opacity .4s cubic-bezier(.4,0,.6,1) .05s` + `transform .5s` (fade con
  leggero ritardo); hover colore `.32s`; micro-feedback 80–100ms lineare.

---

## 2. Miro (sito marketing, costruito con Framer + Tailwind)

### Font e pesi
- Titoli: **Roobert PRO Medium** (~90 variabili `--framer-font-family`); corpo: **Noto Sans**
  (×69) e **Inter** (×42); mono: Fragment Mono.
- Pesi: 400 ×20, 600 ×18, 700 ×18, 500 ×11 (+ 47/47 per 400/600 nelle variabili Framer).
- Feature OpenType attive su Inter: `cv03 cv04 cv09 cv11` (forme alternative più "umane").

### Tipografia
font-size 32px ×7, 24px ×6 (+21 var), 14px ×24 (var), 16/18px ×4, 40/48px ×4–14.
Line-height **115%** per titoli ×8, 145% per corpo. Tracking titoli **-0.03em** ×6, -0.02em ×2.

### Colori
| Ruolo | Valore | Occorrenze |
| --- | --- | --- |
| Testo / superficie scura | `#1c1c1e` rgb(28,28,30) | 206 |
| Bianco | `#ffffff` | 121 |
| Link | rgb(0,153,255) | 73 |
| Accento CTA | rgb(56,89,255) / `#4262ff` | 7+ |
| Grigio superficie | rgb(241,242,245) | 41 |
| Bordi / hairline | `rgba(0,0,0,.04–.10)` | 70+ |
| Pastelli canvas | `#c3f4d6`, `#e1fbf9`, `#fffae7`, `#e3f7ea`, `#ffe6cd`, `#e5e2ff` | 12 ciascuno |

I pastelli sono i colori degli oggetti sulla lavagna (sticky, aree): servono a
distinguere categorie senza saturare.

### Raggi
12px ×5, 8px ×5, 16px ×3, 20px ×2, 40px ×2, 6px ×2, 4px ×2, `50%` ×6. Base Tailwind `--radius`.

### Ombre
Stile Framer "a strati sottili": `0 0.74px 0.67px -0.75px rgba(0,0,0,.x)` ×12 e varianti
(più livelli impilati con spread negativo). Card: `0 1px 8px rgba(0,0,0,.06)`,
`0 2px 8px #0000001f`, bordo come ombra `0 0 0 1px rgb(224,226,232)`.
Focus: doppio anello `0 0 0 1px blue-500, 0 0 0 2px …`. Vetro leggero: `blur(8px)` ×4.

### Movimento
`ease` ×25, `ease-out` ×8, `cubic-bezier(0.4,0,1,1)` ×8; durate 100ms ×9, 200ms ×13,
150ms ×6. Tutto rapido: `transform .2s ease` ×6, `background .15s, transform .1s`.

### UX osservata (screenshot)
Hero = composer di chat AI al centro, collegato con curve a oggetti (tabella, documento,
diagramma BPMN con corsie). Nav a capsula flottante, bianca, raggio ~16px, staccata dal bordo.

---

## 3. Lucidchart (sito marketing)

### Font e pesi
**Graphik** (corpo, ×72) e **GraphikWide** (titoli, ×21). Pesi via token:
400 ×68, 500 ×40, 700 ×37, 900 ×16, 300 ×9, 600 ×10.

### Scala (token `--font-sizes-*`)
8, 10, 12, 16, 20, 24, 32, 40, 48, 64, 80, 100, 120px.
Uso: fs32 ×48, fs20 ×39, fs16 ×35, fs24 ×33, fs40 ×28, fs48 ×19, fs64 ×14, fs12 ×13.
Line-height token: 1 ×46, 1.35 ×20, 1.1 ×17, 1.5, 1.2, 1.75. Tracking unico `-0.2px` ×61.

### Colori (scale 0–100)
- Grigio freddo: `#fafbfc` → `#f2f3f5` → `#dfe3e8` → `#ced4db` → `#a9afb8` → `#838a93` →
  `#6f7681` → `#4c535d` → `#3a414a` → **`#282c33`** (testo, ×9 diretto + token).
- Blu: `#edf5ff` → `#cfe4ff` → `#6db1ff` → `#2888fa` → **`#1071e5`** → `#005ed0` → `#002a5e`.
- Arancio brand: `#fff3d9` → `#fa7811` → **`#eb5a00`** → `#4f1e00`.

### Raggi (`--radii-*`)
2, 4, 8, 12, 16, 24, 32, 48px. Uso: r2 ×7, r4 ×5, `50%` ×8, `9999px` ×4. Prevalgono angoli
**piccoli (2–4px)**: estetica da strumento tecnico.

### Ombre
Sistema a elevazione con offset diagonale: `elevation1 1px 1px 2px rgba(40,44,51,.24)`,
`elevation2 2px 2px 4px …/.2`, `elevation3 4px 4px 6px …/.16`; card hover `6px 6px 8px …/.12`.
Bordi di stato come inset: `inset 0 0 0 1px var(--colors-*-20)`.

### Movimento
Token: `--easings-end cubic-bezier(0.05,0,0,1)`, `--easings-slow-start cubic-bezier(.33,0,.25,1)`,
`--easings-fast-end cubic-bezier(.75,0,.67,1)`. Uso diretto: `ease` ×23, `ease-out` ×19,
`ease-in-out` ×18. Durate: **200ms ×31**, 300ms ×18, 250ms ×10, 150ms ×8.

### UX osservata (screenshot)
Editor: rail verticale di strumenti a sinistra (icone 16px in colonna da ~32px), toolbar di
formattazione flottante e compatta in alto, tab delle pagine e zoom in una barra inferiore
sottile. Molto denso, nessuna decorazione.

---

## 4. ChatGPT (app, schermata iniziale non loggata)

Il browser headless di REA riceve la verifica anti-bot di Cloudflare. Ispezione fatta in modo
passivo (`inspect_web_page` + `capture_web_screenshot`) su un Chrome aperto dall'utente con
`--remote-debugging-port=9333` e profilo separato. Vista: sidebar + stato vuoto + composer,
viewport 1685×1239, tema scuro. **Non osservata**: una conversazione con messaggi; servirebbe
che l'utente scriva un messaggio mentre REA osserva.

### Font e pesi
- Nessun file font caricato. Stack principale: `-apple-system, BlinkMacSystemFont,
  "OpenAI Sans", sans-serif`; mono `SF Mono, SFMono-Regular, ui-monospace, Consolas`.
- Pesi: 600 ×12, 500 ×11, 400 ×8, più pesi variabili fini (510 ×3, 550 ×2, 590 ×2).

### Tipografia
font-size 14px/.875rem ×7, 16px/1rem ×8, 13px/.8125rem ×6, 24px/1.5rem ×8, 28px ×3, 36px ×4,
11px/.6875rem ×3. Line-height in rem: 1.25rem ×7 (su 14px), 1.5rem ×4 (su 16px), 26–34px su titoli.
Tracking negativo leggero: -.01em ×3, -.025em ×3, -.02em ×2, valori px fra -0.08 e -0.44.

### Colori (token semantici, coppia chiaro / scuro)
| Token | Chiaro | Scuro |
| --- | --- | --- |
| `surface` | `#fcfcfc` | `#000` |
| `surface-elevated` | `#fff` | `#1c1c1c` |
| `surface-tertiary` (composer, pillole) | `#eee` | `#2a2a2a` |
| `text-primary` / `prose` | `#0d0d0d` | `#fff` |
| `text` | `#282828` | `#dcdcdc` |
| `text-secondary` | `#5d5d5d` | `#afafaf` |
| `text-disabled` | `#8f8f8f` | `#5d5d5d` |
| `border` | `#0d0d0d1a` (10%) | `#ffffff1f` (12%) |
| `border-subtle` | `#0d0d0d0d` (5%) | `#ffffff0f` (6%) |
| `border-*-outline` | `#0d0d0d29` (16%) | `#ffffff40` (25%) |
| `background-primary-solid` (pulsante pieno) | `#181818` | `#f3f3f3` |
| `ghost-hover` / `ghost-active` | nero 8% / 12% | bianco 12% / 16% |
| `ring` (focus) | `#0169cc` | `#0285ff` |
| success / danger / warning / info / discovery | `#008635` / `#ba2623` / `#923b0f` / `#004f99` / `#6b3ab4` | `#04b84c` / `#fa423e` / `#fb6a22` / `#339cff` / `#be95fa` |

Il pulsante primario **non è colorato**: è nero pieno in chiaro e quasi bianco in scuro.
Il blu compare solo nel focus. Hover e active si fanno con velature alfa (8/12/16%), non
con colori diversi. Bordi sempre in alfa, mai grigi pieni.

### Raggi
`999px` ×7 (composer, pulsanti, pillole), .5rem/8px ×7, .875rem/14px ×6, .625rem/10px ×5,
1rem ×5, 1.5rem/24px ×5, 28px ×5, 1.75rem ×3, .25rem ×4. Select: 6/8px o capsula.

### Ombre e vetro
Morbide e molto diffuse: `0 4px 16px #0000000d` ×8 (card, composer), Tailwind
`0 10px 15px -3px #0000001a, 0 4px 6px -4px #0000001a` ×3, popover
`0 1.5rem 4rem #00000038, 0 .25rem 1rem #0000001f` ×2. Bordi come ombra
`inset 0 0 0 1px var(--color-border-*-outline)`. Vetro su overlay: `blur(24px) saturate(1.2)`,
`blur(25px) saturate(1.12)`, `blur(12px)`.

### Movimento
Easing: `ease` ×30, **`cubic-bezier(.16,1,.3,1)` ×10** (expo-out, entrata decisa),
`cubic-bezier(.2,0,0,1)` ×8, `cubic-bezier(.19,1,.22,1)` ×5, `cubic-bezier(.2,.8,.2,1)` ×5.
Durate: **150ms ×36** (hover, colori, opacità), 200ms ×13, 220ms ×8, 250ms ×7, 300ms ×7.
Variabili `--stream-content-reference-delay` e `--stream-border-accent-color` governano
l'animazione del testo in streaming.

### Layout e UX osservati
- Sidebar ~325px, voci con icona 20px + label, nessun separatore fra le voci; blocco
  "accedi" in fondo.
- Stato vuoto: una sola domanda centrata ("Da dove iniziamo?", ~28px) sopra il composer.
- Composer a capsula, ~960px di larghezza su 1685px, alto ~64px: `+` allegati a sinistra,
  microfono e invio circolare a destra; invio disattivato finché il campo è vuoto.
- Tooltip scuri, piccoli (13px, raggio ~8px).
- Thread centrato in griglia con colonne nominate (`full`, `content`, `primary`); su mobile
  margini 0.625–1.5rem, maschera di sfumatura sopra/sotto e spazio riservato al composer
  (`--mobile-thread-composer-reserve`) calcolato sull'altezza della tastiera.

---

## 5. Sintesi per DeliR

Cosa convergono i riferimenti, rispetto al Satin attuale:

| Aspetto | Apple | Miro | Lucid | ChatGPT | Indicazione per DeliR |
| --- | --- | --- | --- | --- | --- |
| Pesi | 400 + 600 | 400/500/600 | 400/500/700 | 400/500/600 | Ridurre a **400 + 600** (500 solo label) |
| Corpo base | 17px | 14–16px | 16px | 14px UI, 16px prosa | App densa: **14px** UI, 16px testo chat |
| Tracking | ottico, -0.022em a 17px | -0.03em titoli | -0.2px | -.01/-.025em | Negativo leggero sotto 20px e sopra 32px |
| Palette | neutri + 1 blu | neutri + blu + pastelli | grigi freddi + blu | neutri, primario nero/bianco, blu solo focus | Neutri + **un accento**; pastelli solo per categorie sul canvas |
| Gerarchia testo | grigi #1d1d1f / #6e6e73 / #86868b + velature nero .48–.64 | grigi | scala grigi | #0d0d0d / #5d5d5d / #8f8f8f | 3 livelli: primario / secondario / terziario |
| Hover/active | colore pieno più scuro | — | — | velature alfa 8/12/16% | Velature alfa: funzionano uguali in chiaro e scuro |
| Bordi | `#d2d2d7` | alfa 4–10% | grigi pieni | alfa 5/10/16% | Hairline in alfa |
| Raggi | capsula + 8–28px | 8–20px | 2–8px | capsula + 8–28px | Capsula per azioni/composer, 12px card, 8px controlli, 4px nodi/tabella |
| Ombre | quasi zero, vetro blur 20px | strati sottilissimi | elevazioni piccole | morbide diffuse 0 4px 16px 5% | Profondità con sfondo + hairline; ombra solo su elementi flottanti |
| Focus | doppio anello 3px+2px | doppio anello 1+1px | inset | anello blu `#0169cc` | Doppio anello visibile, colore accento |
| Easing | `cubic-bezier(.4,0,.6,1)` | `ease` | `cubic-bezier(.05,0,0,1)` | `ease` + `(.16,1,.3,1)` | Standard `(.4,0,.6,1)`, entrata `(.16,1,.3,1)` |
| Durate | 240 / 400 / 80ms | 100–200ms | 200ms | 150ms | 80ms feedback, 150ms hover, 240ms UI, 400ms pannelli |

Prossimi passi proposti:
1. Confrontare questi valori con `frontend/styles/tokens/primitive.css` e `semantic.css`
   (durate 70/110/150/240/400/700 e raggi 2–32px già vicini).
2. Screenshot della UI DeliR (chat, canvas, desktop e mobile) e audit contro questa sintesi.
3. ChatGPT: osservare una conversazione vera (bolle utente, prosa assistente, streaming,
   azioni sul messaggio), con l'utente che scrive mentre REA osserva.

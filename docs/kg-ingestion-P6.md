# P6 — Ingestione multi-sorgente (L3): dagli input del consulente al grafo

> Spec di riferimento. P6 non è "upload PDF": è **la porta d'ingresso
> multi-sorgente del Cervello DeliR**. Dipende da **P5** (`kg_ingest_queue`).

## 1. Perché

Oggi l'unico modo per far entrare testo nel KG è incollarlo in chat
(`raw_content` → `manage_process_evidence` → `mirror` → `enqueue_evidence`).
Il consulente deve spezzare a mano interviste da 30 pagine, manuali PDF, export
gestionali. Metà del valore di "DeliR legge la roba del cliente" non c'è.

Con P6: il consulente butta dentro i file / streamma l'intervista → DeliR
parsa, chunka, embedda, **estrae il KG da solo** (nuovo, oggi lo fa l'agente
con args strutturati), tutto ricercabile con provenance ("manuale p.12",
"intervista 14:32").

## 2. Cosa usa il consulente per ricostruire un processo

### Interviste / workshop (fonte primaria)

| input | formato | note |
|---|---|---|
| registrazione call 1:1 | mp3, m4a, wav | Teams/Zoom/telefono |
| registrazione workshop | mp4, mov | estrarre traccia audio |
| intervista live | stream | trascrizione real-time |
| note a mano | foto png/jpg | OCR |
| note digitate | txt, docx, chat | già funziona |

### Documenti del cliente

| input | formato |
|---|---|
| manuali di processo / SOP / istruzioni operative | docx, pdf |
| organigramma | pdf, pptx, immagine, vsdx |
| mappe di processo esistenti | .bpmn/.xml, Visio .vsdx, foto flowchart, export Lucidchart/Miro |
| policy / procedure | pdf, docx |
| moduli / template del processo | pdf, xlsx, docx |
| contratti / SLA | pdf |
| slide training / onboarding | pptx, pdf |
| matrici RACI | xlsx |

### Evidenza dai sistemi ("come gira davvero")

| input | formato | note |
|---|---|---|
| export ERP/CRM/ticketing | csv, xlsx, json/xml | SAP, Salesforce, ServiceNow, Jira, Zendesk |
| **event log / process mining** | **csv, XES** | Celonis/Signavio/Disco |
| screenshot schermate | png/jpg | OCR + layout |
| screen recording / task mining | mp4 | v2 |
| dump DB / query | csv | |
| payload API | json | |

### Comunicazioni

| input | formato | note |
|---|---|---|
| thread email | .eml, .msg, .pst | gli handoff veri |
| export chat (Teams/Slack) | json, html | |
| coda mailbox condivisa | csv | |

### Fogli di calcolo (processi ombra)

| input | note |
|---|---|
| spreadsheet di tracking | l'Excel che qualcuno tiene E CHE È il processo |
| dashboard KPI | xlsx, export Power BI |
| modelli di calcolo | xlsx con formule (la logica è nelle formule) |

### Osservazione / meta

- osservazioni del consulente (digitate)
- foto Gemba walk (immagini)
- time study (xlsx)
- intranet / wiki / Confluence / SharePoint (html, export md)
- foto lavagna (immagine → vision)

## 3. Pipeline + libreria per tipo

Spina dorsale:
`acquisisci → estrai testo grezzo → normalizza + segmenta → metadata → kg_source (+ blob originale) → chunk + embed → estrai KG (LLM) → write_evidence → grafo`

### Testo-nativo

| formato | libreria | note |
|---|---|---|
| txt / md | stdlib + `charset-normalizer` | encoding |
| docx | `docx2txt` (c'è) plain · **`python-docx`** per struttura (heading, tabelle, liste) | |
| doc | LibreOffice headless / `unstructured` | |
| pdf text layer | **`pymupdf`** (c'è) — layout + n. pagina · `pypdf` fallback | |
| pdf scansionato | **`pdf2image`** (+ poppler) → **`pytesseract`** (c'è) · **meglio cloud**: Azure Document Intelligence / AWS Textract per tabelle+moduli+manoscritto | |
| rtf | `striprtf` | |
| html / URL | `beautifulsoup4` (c'è) + **`trafilatura`** (main content) + `httpx` (c'è) | |
| pptx | **`python-pptx`** (testo per slide + note) | |

### Tabellare

| formato | libreria | note |
|---|---|---|
| csv / tsv | `pandas` (c'è) + `csv.Sniffer` | delimiter/encoding |
| xlsx | `pandas.read_excel` + **`openpyxl`** (DA AGGIUNGERE) · multi-sheet · `data_only=False` per le formule | |
| xls | **`xlrd`** o LibreOffice | |

Tabellare → testo: 3 rappresentazioni — (a) tabella markdown se piccola,
(b) frasi "colonna: valore" per riga, (c) schema + righe campione se enorme.
Spesso una tabella è un **event log** → process mining diretto (§ mining).

### Email

| formato | libreria |
|---|---|
| .eml | `email` stdlib · thread via `References`/`In-Reply-To` |
| .msg (Outlook) | **`extract-msg`** |
| .pst | **`libpff`/`pypff`** (pesante) o `readpst` |

### Audio / video

| formato | tech | stato |
|---|---|---|
| audio | OpenAI `gpt-4o-transcribe-diarize` (c'è) — turni speaker · **`ffmpeg`** + **`pydub`** per split file > 25 MB su silenzio | trascrizione ✅, collante ❌ |
| video | **`ffmpeg`** estrai audio → pipeline audio | |
| stream live | WS `gpt-realtime-whisper` (c'è) — accumula → a fine sessione `kg_source` | metà ✅ |
| alternative | AssemblyAI / Deepgram — diarization + speaker label migliori | opzionale |

### Diagrammi / immagini

| formato | tech |
|---|---|
| foto flowchart / lavagna | **vision LLM** (`gpt-4o` vision) descrive topologia + OCR label |
| .bpmn / .xml | parse diretto — È un modello, importabile come candidato (l'app ha già handling BPMN) |
| .vsdx (Visio) | **`vsdx`** lib o conversione — shape + connettori |
| screenshot sistemi | vision LLM + OCR |

### Process mining

| formato | libreria | valore |
|---|---|---|
| .xes (standard IEEE) | **`pm4py`** (grossa) | parsing |
| csv event log (case_id, activity, timestamp, resource) | rilevamento colonne (euristica + LLM) → **`pm4py`** inductive/heuristic miner | **modello scoperto + statistiche = oro per l'AS-IS** |
| Celonis / Signavio / Disco export | csv/xes sotto | |

### Archivi

- .zip / cartella → ricorsione, classifica ogni file, ingerisci tutto
- export SharePoint / Confluence / Notion → bundle html/markdown

## 4. Trasversali (dentro ogni adapter)

| tema | tech |
|---|---|
| rilevamento tipo file (non l'estensione) | **`filetype`** (pure-python) o `python-magic` (libmagic) — MIME sniffing |
| dedup | `content_hash` (c'è in `kg_source`) + near-dup |
| chunking per tipo | prosa: ricorsivo ~1600 char (c'è) · tabelle: gruppo righe · trascrizioni: per turno / finestra temporale |
| metadata | LLM classifica: titolo, autore, data, tipo doc, quale processo/attore, flag riservatezza |
| **PII / B+ (INV-5)** | **`presidio-analyzer`** (Microsoft) o pass LLM — redazione PRIMA che esca da Postgres (nomi, importi, clausole) |
| lingua | `langdetect` — IT/EN |
| file grossi | streaming: pagina-per-pagina, chunk audio, batch di righe — mai 500 MB in RAM |
| isolamento fallimenti | una pagina/sheet storto non uccide il doc |
| provenance nei chunk | file + pagina/sheet/timestamp → l'agente cita la fonte esatta |
| storage originale | `kg_source.blob_uri` (colonna c'è) — dir locale per MVP, object store poi. Tieni l'originale per ri-parsare |
| costo | budget per sorgente / progetto (OCR + vision + trascrizione + estrazione costano) |
| incrementale | export gestionale settimanale → delta, non re-ingest totale |

## 5. Librerie da aggiungere

**Must**:
```
openpyxl          # .xlsx
python-docx       # struttura .docx
python-pptx       # .pptx
extract-msg       # Outlook .msg
pdf2image         # pdf scansionato → immagini (+ binario poppler)
filetype          # MIME sniffing
pydub             # split audio (+ binario ffmpeg)
```

**Forte candidato**:
```
pm4py             # event log → process discovery (feature killer per AS-IS da dati)
trafilatura       # web/HTML main content
presidio-analyzer # PII gate per B+
```

Da valutare: `unstructured[all-docs]` (1 lib molti formati, pesante, meno
controllo vs adapter dedicati).

**Binari di sistema**: `ffmpeg`, `tesseract`, `poppler`.

**Cloud (qualità > costo + vendor)**: Azure Document Intelligence / AWS
Textract (moduli+tabelle+manoscritto); AssemblyAI / Deepgram (diarization).

## 6. Nuovo pezzo: l'estrattore KG automatico

Oggi la struttura del KG (entità, relazioni tipizzate, claim, gap,
contraddizioni, impatti) la fornisce **l'agente** negli argomenti del tool.
Un documento non ha un turno di agente → serve un passo di estrazione:

`backend/kg_ingestion/extractor.py` — LLM `temperature=0` + `with_structured_output`
(pattern di `process_understanding` / `entity_resolution`), iniettabile e fake
nei test. Input: gruppo di chunk + contesto processo/progetto. Output:
`KnowledgeGraphRelationship[]` / `KnowledgeGraphClaim[]` / entità / gap
(`backend/memory/knowledge_graph/models.py`). Poi → `enqueue_evidence(...)`.

## 7. Taglio in sotto-fasi (una PR ciascuna)

| fase | contenuto | dipende |
|---|---|---|
| **P6.0** spina | migration `kg_source` +`origin_kind`/`parse_status`/`parse_meta` · blob store locale · `SourceAdapter` Protocol + registry + `PlainTextAdapter` + fallback · `backend/kg_ingestion/` · **extractor** LLM (§6) · `POST /v1/kg/sources` (multipart) → sniff → adapter → parse → estrai → `enqueue_evidence` · E2E: upload .txt → chunk + entità nel grafo | **P5** |
| **P6.1** documenti | PDF (`pymupdf`) · Word (`python-docx`) · md/txt · HTML/URL (`trafilatura`) | P6.0 |
| **P6.2** tabellare | CSV · XLSX (`openpyxl`) · euristiche export gestionale (rilevamento colonne, summary file grandi) | P6.0 |
| **P6.3** audio | `/v1/audio/transcriptions` → `kg_source` `interview_transcript` · split file lunghi (ffmpeg/pydub) · stream live → ingestione a fine sessione | P6.0 |
| **P6.4** OCR + immagini | pdf scansionato (pdf2image+tesseract o cloud) · foto flowchart/lavagna (vision LLM) · screenshot | P6.1 |
| **P6.5** email | .eml + .msg · ricostruzione thread | P6.0 |
| **P6.6** process mining | XES + CSV event log → `pm4py` discovery → modello scoperto + statistiche come evidenza | P6.0 (grossa) |
| **P6.7** UI | drop-zone nel processo · stato ingestione (`/v1/observability/queues`) · review per-sorgente prima del grafo · bridge `workspace sources` ↔ `kg_source` | P6.1–6.3 |
| trasversale | PII/redazione, sniffing, dedup, provenance, budget — dentro ogni fase | |

**Priorità MVP "dallo al consulente"**: **P6.0 → P6.1 → P6.3 (audio) → P6.2
(tabellare)** — copre interviste (audio + note) + documenti cliente + export
sistemi. OCR / email / mining = v2.

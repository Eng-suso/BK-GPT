# DeliR — Satin design system

Decisione di prodotto, 2026-09-08: applicare a tutta l'interfaccia l'identità
del riferimento fornito da Sohay: vetro bianco satinato, doppia cornice luminosa,
rilievi morbidi e controlli a capsula. Il riferimento riguarda l'aspetto, non
le etichette o le funzionalità mostrate nell'immagine.

## Fonti implementative

- `frontend/src/styles/theme.css`: token semantici, materiali, raggi e ombre.
- `frontend/src/styles/materials.css`: ricette condivise, stati e fallback.
- `frontend/src/ui/surface.tsx`: `Surface` e `surfaceVariants`.
- Storybook: **Design System / Satin materials**.

## Superfici riproducibili

| Variante | Uso |
| --- | --- |
| `panel` | Card, tabelle, pannelli operativi, contenitori di grafici |
| `inset` | Dati secondari, metriche, gruppi di impostazioni |
| `chrome` | Navigazione, intestazioni, pannelli laterali |
| `rail` | Cronologia e navigazione secondaria: superficie fredda distinta dal contenuto |
| `toolbar` | Intestazioni e footer delle tabelle, barre strumenti |
| `floating` | Dialog, popover, superfici sovrapposte |
| `framed` | Composer: doppio involucro luminoso, spazio esterno minimo 7px |

```tsx
<Surface asChild variant="panel" className="p-4">
  <section aria-label="Stato progetto">…</section>
</Surface>
```

Per un elemento esistente usare `surfaceVariants({ variant: "panel" })`,
oppure le classi `ui-surface ui-surface-panel` quando si mantiene un layout
legacy. La superficie non impone padding, dimensioni o stato applicativo.

## Componenti

Usare `Button`, `Input`, `Textarea`, `Select`, `Card`, `Dialog`, `DropdownMenu`,
`Popover`, `Tabs`, `PanelShell`, `DataTable`, `StatTile` e `ListToolbar`.
Sono i punti di adozione condivisi. Evitare nuove copie di ombre e bordi.

Per avvisi contestuali usare `InlineNotice`: icona semantica, testo e azione
compatti, con fondo neutro. Nella chat segue la larghezza di lettura e non
mostra indirizzi o dettagli tecnici della connessione. Il colore di stato
serve a identificare l'avviso, senza riempire di giallo l'intera schermata.

Le superfici legacy della chat incorporata devono mantenere gli stessi token
del composer principale; non sovrascrivere cornice e ombra con bianco pieno
o `box-shadow: none`.

Il composer comprende campo senza bordo interno, area comandi e cornice.
Durante l'esecuzione Ferma sostituisce Invia nello stesso spazio; la bozza si
conserva. Le attività sono espandibili e mantengono il tempo totale visibile.

## Regole visive e funzionali

- Neutri caldi/freddi molto leggeri, superfici quasi opache, bordi luminosi.
- Blu DeliR per azioni principali, selezione e focus; non per ogni contorno.
- Testi scuri, stato/errori espliciti: profondità e trasparenza non sono gli
  unici segnali interattivi.
- Nessun blur su ogni riga di tabella o forma BPMN. Sfocatura sulle superfici
  sovrapposte; canvas e grafici conservano contrasto e semantica.
- Mantenere densità, scroll, dimensionamento del canvas e ordine da tastiera.
- Focus visibile, modalità forced-colors e reduced-motion; superfici opache
  con reduced-transparency o senza supporto backdrop-filter.
- DeliR mantiene il tema chiaro e la tipografia Geist esistenti.

## Verifica

Controllare chat/composer e menu, liste e filtri, form/dialog, canvas con
ispettore e simulazione. Verificare desktop e mobile, apertura da tastiera,
ritorno del focus, overflow, contrasto e conservazione delle bozze.

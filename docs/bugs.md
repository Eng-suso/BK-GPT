# Bug log

Un bug per sezione, con la frase che lo ha prodotto. Lo stato dice se la
regressione e' coperta da un test, non se "sembra a posto".

## CLIENT-01 — Status cliente non inferito dal linguaggio

- **Severity**: P2
- **Stato**: risolto (2026-09-06) — coperto da `tests/test_client_status.py`
- **Input**: "Ho acquisito un nuovo cliente: Esaote S.p.A."
- **Expected**: cliente registrato con uno stato coerente con "acquisito" (`Attivo`).
- **Actual**: `Prospect`. L'agente rispondeva "Ho acquisito un nuovo cliente" mentre
  scriveva a database il contrario: un prospect e' qualcuno che stai *ancora*
  cercando di acquisire.
- **Causa**: `status="Prospect"` era il default hard-coded di ogni punto di
  ingresso — `ClientRecordInput`, `InitialWorkspaceSetupInput`,
  `CreateClientRequest`, `create_client`, piu' le istruzioni in
  `how_to_act.md`. Il modello non aveva una scelta da fare: il campo era gia'
  risposto.

### Fix

`backend/workspace_defaults.py` raccoglie il vocabolario degli stati e il
significato di "non lo so":

- ogni punto di ingresso ha default `None` = "non dichiarato";
- il tool schema espone `Literal["Attivo", "Da seguire", "Prospect"]` con una
  descrizione che dice *quando* valorizzarlo, quindi il modello sceglie;
- il placeholder (`Prospect`) si applica una volta sola, al confine col
  database, e significa solo "nessuno lo ha deciso";
- `create_client` resta idempotente per nome e riempie i soli campi rimasti al
  placeholder: una create ripetuta non duplica e non butta via l'informazione
  arrivata dopo, ma non sovrascrive un valore gia' deciso (cambiarlo e' un
  update, e `create_client` non lo e').

### Verifica

`tests/test_client_status.py` copre vocabolario, contratto dei quattro punti di
ingresso (il default hard-coded non puo' tornare) e comportamento reale su
Postgres, idempotenza inclusa.

Controllo con modello reale, fuori CI (`gpt-4.1-mini`, tool `manage_client_record`):

| frase | `status` scelto |
| --- | --- |
| "Ho acquisito un nuovo cliente: Esaote S.p.A." | `Attivo` |
| "Sto cercando di acquisire Barilla, per ora e' solo un contatto." | `Prospect` |
| "Aggiungi Ferrari come cliente." | non valorizzato → placeholder `Prospect` |

L'ultima riga resta un caso limite noto: "come cliente" e' debole, il modello
non se la sente e lascia decidere al placeholder. Accettabile finche' il
placeholder significa "sconosciuto"; se dovesse diventare fastidioso, la leva e'
la descrizione del campo, non un default nuovo.

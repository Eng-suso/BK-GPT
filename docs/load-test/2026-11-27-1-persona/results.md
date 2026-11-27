# Test di carico: 1 persone per 3.0 minuti

Durata reale 191.1 s. Modello finto: primo token dopo 800 ms, 40 token/s.

| Operazione | Riuscite | Errori | p50 (s) | p95 (s) | max (s) |
|---|---:|---:|---:|---:|---:|
| auth_me | 1 | 0 | 0.013 | 0.013 | 0.013 |
| chat_first_token | 12 | 0 | 6.547 | 10.382 | 10.587 |
| chat_turn | 12 | 0 | 6.556 | 10.392 | 10.603 |
| create_chat | 1 | 0 | 0.011 | 0.011 | 0.011 |
| create_client | 1 | 0 | 0.013 | 0.013 | 0.013 |
| create_process | 1 | 0 | 0.012 | 0.012 | 0.012 |
| create_project | 1 | 0 | 0.011 | 0.011 | 0.011 |
| list_chats | 12 | 0 | 0.005 | 0.006 | 0.007 |
| list_clients | 12 | 0 | 0.007 | 0.008 | 0.008 |
| list_projects | 12 | 0 | 0.01 | 0.014 | 0.017 |
| simulation_poll | 4 | 0 | 0.01 | 0.016 | 0.016 |
| simulation_start | 4 | 0 | 0.016 | 0.018 | 0.018 |
| simulation_total | 4 | 0 | 2.028 | 2.031 | 2.031 |
| usage_me | 12 | 0 | 0.005 | 0.006 | 0.007 |

Picchi: memoria dell'app 574 MB, 43 thread, 19 connessioni Postgres (3 attive insieme).


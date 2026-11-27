# Test di carico: 10 persone per 5.0 minuti

Durata reale 318.4 s. Modello finto: primo token dopo 800 ms, 40 token/s.

| Operazione | Riuscite | Errori | p50 (s) | p95 (s) | max (s) |
|---|---:|---:|---:|---:|---:|
| auth_me | 10 | 0 | 0.024 | 0.028 | 0.028 |
| chat_first_token | 204 | 0 | 6.62 | 10.777 | 10.971 |
| chat_turn | 204 | 0 | 6.643 | 10.789 | 10.983 |
| create_chat | 10 | 0 | 0.107 | 0.124 | 0.124 |
| create_client | 10 | 0 | 0.073 | 0.083 | 0.083 |
| create_process | 10 | 0 | 0.099 | 0.11 | 0.11 |
| create_project | 10 | 0 | 0.077 | 0.08 | 0.08 |
| list_chats | 204 | 0 | 0.006 | 0.011 | 0.057 |
| list_clients | 204 | 0 | 0.008 | 0.023 | 0.063 |
| list_projects | 204 | 0 | 0.011 | 0.029 | 0.338 |
| simulation_poll | 69 | 0 | 0.01 | 0.02 | 0.033 |
| simulation_start | 69 | 0 | 0.018 | 0.034 | 0.075 |
| simulation_total | 69 | 0 | 2.032 | 2.051 | 2.087 |
| usage_me | 204 | 0 | 0.007 | 0.016 | 0.026 |

Picchi: memoria dell'app 575 MB, 183 thread, 19 connessioni Postgres (1 attive insieme).


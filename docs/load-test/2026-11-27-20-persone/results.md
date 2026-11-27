# Test di carico: 20 persone per 5.0 minuti

Durata reale 317.7 s. Modello finto: primo token dopo 800 ms, 40 token/s.

| Operazione | Riuscite | Errori | p50 (s) | p95 (s) | max (s) |
|---|---:|---:|---:|---:|---:|
| auth_me | 20 | 0 | 0.05 | 0.057 | 0.057 |
| chat_first_token | 405 | 0 | 6.652 | 10.74 | 11.312 |
| chat_turn | 405 | 0 | 6.669 | 10.771 | 11.323 |
| create_chat | 20 | 0 | 0.137 | 0.188 | 0.195 |
| create_client | 20 | 0 | 0.124 | 0.185 | 0.209 |
| create_process | 20 | 0 | 0.147 | 0.195 | 0.23 |
| create_project | 20 | 0 | 0.134 | 0.161 | 0.185 |
| list_chats | 405 | 0 | 0.006 | 0.014 | 0.041 |
| list_clients | 405 | 0 | 0.009 | 0.025 | 0.074 |
| list_projects | 405 | 0 | 0.011 | 0.032 | 0.543 |
| simulation_poll | 137 | 0 | 0.011 | 0.026 | 0.074 |
| simulation_start | 137 | 0 | 0.019 | 0.041 | 0.465 |
| simulation_total | 137 | 0 | 2.033 | 2.065 | 2.476 |
| usage_me | 405 | 0 | 0.007 | 0.019 | 0.51 |

Picchi: memoria dell'app 586 MB, 325 thread, 17 connessioni Postgres (2 attive insieme).


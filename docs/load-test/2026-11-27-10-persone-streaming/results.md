# Test di carico: 10 persone per 5.0 minuti

Durata reale 309.3 s. Modello finto: primo token dopo 800 ms, 40 token/s.

| Operazione | Riuscite | Errori | p50 (s) | p95 (s) | max (s) |
|---|---:|---:|---:|---:|---:|
| auth_me | 10 | 0 | 0.658 | 0.666 | 0.666 |
| chat_first_token | 193 | 0 | 3.585 | 8.025 | 14.267 |
| chat_turn | 193 | 0 | 6.723 | 11.165 | 17.382 |
| create_chat | 10 | 0 | 0.111 | 0.135 | 0.135 |
| create_client | 10 | 0 | 0.149 | 0.173 | 0.173 |
| create_process | 10 | 0 | 0.146 | 0.187 | 0.187 |
| create_project | 10 | 0 | 0.135 | 0.181 | 0.181 |
| list_chats | 193 | 0 | 0.007 | 0.016 | 0.035 |
| list_clients | 193 | 0 | 0.009 | 0.029 | 0.046 |
| list_projects | 193 | 0 | 0.012 | 0.066 | 0.243 |
| simulation_poll | 64 | 0 | 0.011 | 0.05 | 0.255 |
| simulation_start | 64 | 0 | 0.021 | 0.035 | 0.057 |
| simulation_total | 64 | 0 | 2.037 | 2.074 | 2.278 |
| usage_me | 193 | 0 | 0.009 | 0.02 | 0.079 |

Picchi: memoria dell'app 583 MB, 207 thread, 35 connessioni Postgres (3 attive insieme).


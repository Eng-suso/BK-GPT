# Verifica frontend DEV, STAGING e PROD-SIM (2026-11-18)

Il frontend di STAGING e PROD-SIM chiama l'API sulla propria origine, invece
della porta DEV 8000. Prima di caricare il workspace verifica `/v1/auth/me`.
L'utente inserisce tenant e token del singolo ambiente nella sessione del
browser. I file locali `.env` hanno tenant e token diversi; il validatore
confronta eventuali chiavi provider reali anche con il `.env` di root letto
dal backend DEV, oltre che con `ops/.env` e l'altro stack.

| Ambiente | Prova reale in Chrome | Esito |
| --- | --- | --- |
| DEV | Vite 3030 e FastAPI 8000 avviati temporaneamente con worker e migrazioni automatiche disattivati | `/v1/auth/me` 200 sulla 8000, nessun form token, workspace caricato senza errore. I processi temporanei sono stati fermati; i container dati DEV non sono stati toccati. |
| STAGING | Immagine ricostruita e full stack `healthy`; Chrome desktop 1280 e mobile 390 | Il primo `/v1/auth/me` ha risposto 403; con tenant/token STAGING ha risposto 200, workspace caricato senza errore. Stack fermato con volumi conservati. |
| PROD-SIM | Stessa immagine promossa, full stack `healthy`, readiness 200 | Tenant/token STAGING rifiutati con 403; tenant/token PROD-SIM accettati con 200, workspace caricato senza errore. Stack lasciato avviato. |

Gli ID immagine app STAGING e PROD-SIM, dopo questa build, coincidono:
`sha256:31b919c87ee716ba4ca8633d1c8bcd485495b690958e2d82357688bfbab703d2`.
Frontend lint e typecheck sono passati; 9 test frontend mirati e 7 test
Compose/configurazione sono passati. La prima esecuzione pytest e' stata
bloccata dai permessi sulla cartella temporanea di sistema; la ripetizione
con `--basetemp` nel workspace ha superato tutti i test. Il launcher DEV
standard non e' partito nel sandbox per il fetch di una dipendenza e per
permessi WMI; la prova DEV e' stata eseguita direttamente con il virtualenv
gia' installato e con i worker spenti.

Resta un limite di sicurezza distinto: la trascrizione audio live passa il
token API nella query string del WebSocket esistente. La verifica qui non
copre quella funzione. Evitare la trascrizione live negli ambienti protetti
finche' l'autenticazione del WebSocket non viene riprogettata.

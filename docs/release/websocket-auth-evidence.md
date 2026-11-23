# Trascrizione live: autenticazione WebSocket (2026-11-23)

Il browser apre `/v1/audio/live-transcription` senza parametri di credenziali.
Nel primo frame invia `type=auth`, tenant e token della sessione corrente.
Il server accetta il WebSocket, attende il frame per un massimo di cinque
secondi e valida forma, tenant e token prima di aprire la connessione al
provider. I token nella query string non vengono piu' accettati.

## Prove eseguite

| Prova | Risultato |
| --- | --- |
| Test backend del protocollo live | 10 passati; coprono DEV senza auth, token errato, tenant fuori allowlist, token nella vecchia query ignorato e accesso valido con provider simulato. |
| Test frontend del gate e del frame auth | 2 passati; il frame prende tenant e token della sessione corrente. |
| Lint e typecheck frontend | Passati. |
| Build e `up --wait` STAGING | Cinque servizi healthy. Connessione WebSocket con token errato rifiutata con codice 1008. Stack fermato conservando i volumi. |
| Promozione e `up --wait` PROD-SIM | Cinque servizi healthy, `/health/ready` 200, token errato rifiutato con codice 1008. Stack lasciato avviato. |
| Identita' immagine applicativa | STAGING e PROD-SIM: `sha256:2b5ac4f30c0fa592dcfe550c67ca94d49b844d2963cebcca0d16acffa289a9cf`. |

La API DEV locale non era attiva durante questa verifica. Il ramo DEV del
protocollo e' passato nel test applicativo con provider simulato; non viene
qui dichiarata una prova runtime DEV. Non e' stata eseguita una trascrizione
reale: gli stack locali hanno un placeholder per `OPENAI_API_KEY` e non
volevamo chiamare il provider.

Il primo frame contiene comunque una credenziale e deve restare escluso dai
log applicativi e di proxy. Il token resta in `sessionStorage` dell'origine
del browser, secondo il flusso di accesso locale esistente.

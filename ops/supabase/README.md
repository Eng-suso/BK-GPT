# Supabase locale (solo autenticazione)

DeliR usa Supabase **solo** per l'identità dei consulenti (Track B,
[docs/deployment-and-tenancy.md](../../docs/deployment-and-tenancy.md)). I dati
applicativi restano nei Postgres di `ops/`. Questa cartella configura la CLI
locale per dev, E2E e PROD-SIM; staging e produzione usano due progetti cloud
distinti (piano Free, regione UE).

La configurazione sta in `ops/supabase` e non in `supabase/`: l'integrazione
GitHub di Supabase guarda `supabase/` e aprirebbe un preview branch per PR.

## Uso

Dal root del repository:

```powershell
npm run supabase:start    # genera la chiave se manca, poi avvia db + auth + gateway
npm run supabase:status   # URL e chiavi locali (demo, non segrete)
npm run supabase:stop
```

`supabase:start` avvia solo database, GoTrue e Kong (~400 MB): REST, Studio,
Storage, Realtime, Edge Functions, analytics e mail sono spenti.

## Cosa è diverso dai default

| Impostazione | Valore | Perché |
| --- | --- | --- |
| Firma JWT | ES256 da `signing_keys.json` | Il backend accetta solo ES256 via JWKS, come in cloud |
| `enable_signup` | `false` | Si entra solo su invito (B6); gli utenti si creano via admin API |
| `jwt_expiry` | 1800 s | Revoca entro 30 minuti, come deciso in Track B |
| `minimum_password_length` | 12 | |
| `site_url` | `http://127.0.0.1:3030` | Il frontend di sviluppo |

`signing_keys.json` contiene la chiave **privata**: è ignorato da git e ogni
macchina genera la sua.

## Collegare il backend

Nel `.env` del backend:

```dotenv
DELIR_AUTH_ENABLED=true
DELIR_AUTH_PROVIDER=supabase
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_PUBLISHABLE_KEY=<PUBLISHABLE_KEY da npm run supabase:status>
```

Un utente di prova si crea con la `SECRET_KEY` locale:

```powershell
curl.exe -X POST http://127.0.0.1:54321/auth/v1/admin/users `
  -H "apikey: <SECRET_KEY>" -H "Authorization: Bearer <SECRET_KEY>" `
  -H "Content-Type: application/json" `
  -d '{\"email\":\"consulente@delir.test\",\"password\":\"<almeno 12 caratteri>\",\"email_confirm\":true}'
```

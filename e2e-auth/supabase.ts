import { execSync } from 'node:child_process';

/**
 * Il Supabase locale avviato con `npm run supabase:start`. URL e chiavi sono
 * quelli demo della CLI: locali, non segreti, letti a ogni giro e mai scritti
 * in un file del repository.
 */
export type LocalSupabase = { apiUrl: string; publishableKey: string; secretKey: string };

export function localSupabase(): LocalSupabase {
  const raw = execSync('npx supabase status --workdir ops -o json', {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'ignore'],
  });
  const status = JSON.parse(raw.slice(raw.indexOf('{'), raw.lastIndexOf('}') + 1)) as Record<string, string>;
  if (!status.API_URL || !status.PUBLISHABLE_KEY || !status.SECRET_KEY) {
    throw new Error('Supabase locale non avviato: esegui `npm run supabase:start`.');
  }
  return { apiUrl: status.API_URL, publishableKey: status.PUBLISHABLE_KEY, secretKey: status.SECRET_KEY };
}

/** L'utente di prova: esiste solo nel Supabase locale, creato dal global setup. */
export const CONSULTANT = { email: 'consulente.e2e@delir.test', password: 'password-e2e-lunga-123' };
/** Ha un account in Supabase ma non e' fra le persone ammesse (`DELIR_ALLOWED_EMAILS`). */
export const OUTSIDER = { email: 'esterno.e2e@altro.test', password: 'password-e2e-lunga-456' };
export const TENANT = 'local';
/** Il token condiviso del pilota: con Supabase acceso non deve aprire niente. */
export const SHARED_TOKEN = 'token-condiviso-che-con-supabase-non-apre-niente';
export const BACKEND_PORT = Number(process.env.DELIR_E2E_AUTH_BACKEND_PORT ?? 8011);
export const FRONTEND_PORT = Number(process.env.DELIR_E2E_AUTH_FRONTEND_PORT ?? 3032);

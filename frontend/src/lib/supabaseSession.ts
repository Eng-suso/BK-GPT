import type { SupabaseClient } from "@supabase/supabase-js";

import type { AuthConfig } from "./authConfig";
import { clearSessionCredentials, setAccessToken } from "./security";

let client: Promise<SupabaseClient> | null = null;

/**
 * Il client Supabase, creato una volta dalla configurazione letta a runtime.
 *
 * Solo autenticazione: DeliR non legge dati da Supabase. La sessione sta in
 * `sessionStorage` (come il token condiviso prima): chiusa la scheda, si
 * rientra. Ogni login e ogni refresh aggiornano il token in memoria che
 * `authHeaders` manda al backend.
 *
 * La libreria si carica solo qui, con `import()`: gli ambienti col token
 * condiviso non la scaricano, e il bundle d'ingresso resta nel suo budget.
 */
async function supabaseAuth(config: AuthConfig): Promise<SupabaseClient["auth"]> {
  client ??= import("@supabase/supabase-js").then(({ createClient }) => {
    const created = createClient(config.supabaseUrl, config.supabasePublishableKey, {
      auth: {
        storage: window.sessionStorage,
        storageKey: "delir:supabase-session",
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: false,
      },
    });
    created.auth.onAuthStateChange((_event, session) => {
      setAccessToken(session?.access_token ?? null);
    });
    return created;
  });
  return (await client).auth;
}

/** Recupera la sessione gia' aperta in questa scheda, se c'e'. */
export async function restoreSupabaseSession(config: AuthConfig): Promise<boolean> {
  const { data } = await (await supabaseAuth(config)).getSession();
  setAccessToken(data.session?.access_token ?? null);
  return Boolean(data.session);
}

export type SignInResult = "ok" | "invalid" | "unavailable";

export async function signInWithSupabase(
  config: AuthConfig,
  email: string,
  password: string,
): Promise<SignInResult> {
  try {
    const auth = await supabaseAuth(config);
    const { data, error } = await auth.signInWithPassword({ email, password });
    if (error) {
      // 400/422 = credenziali rifiutate. Rete giu' (status 0) o 5xx non sono
      // colpa di chi scrive la password, e non vanno presentati cosi'.
      return error.status === 400 || error.status === 422 ? "invalid" : "unavailable";
    }
    if (!data.session) return "invalid";
    setAccessToken(data.session.access_token);
    return "ok";
  } catch {
    return "unavailable";
  }
}

/** Chiude la sessione in Supabase e dimentica tutto in questa scheda. */
export async function signOutOfSupabase(): Promise<void> {
  try {
    if (client) await (await client).auth.signOut();
  } finally {
    clearSessionCredentials();
  }
}

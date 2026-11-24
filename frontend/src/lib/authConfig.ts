import { z } from "zod";

import { http } from "./http";

/**
 * Come questo ambiente vuole che il browser provi chi e'.
 *
 * Si legge dal backend a runtime e non dal bundle: la stessa build gira in
 * sviluppo, staging, prod-sim e produzione, e solo la configurazione cambia.
 */
export type AuthProvider = "local" | "token" | "supabase";

export type AuthConfig = {
  provider: AuthProvider;
  /** Con `supabase`: l'URL del progetto e la sua chiave publishable. */
  supabaseUrl: string;
  supabasePublishableKey: string;
};

const apiAuthConfigSchema = z.object({
  provider: z.enum(["local", "token", "supabase"]),
  supabase_url: z.string(),
  supabase_publishable_key: z.string(),
});

export async function fetchAuthConfig(): Promise<AuthConfig> {
  const parsed = apiAuthConfigSchema.parse(await http<unknown>("/v1/auth/config"));
  if (parsed.provider === "supabase" && (!parsed.supabase_url || !parsed.supabase_publishable_key)) {
    throw new Error("Configurazione Supabase incompleta");
  }
  return {
    provider: parsed.provider,
    supabaseUrl: parsed.supabase_url,
    supabasePublishableKey: parsed.supabase_publishable_key,
  };
}

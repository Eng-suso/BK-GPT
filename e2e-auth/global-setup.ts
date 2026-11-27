import { CONSULTANT, OUTSIDER, localSupabase } from './supabase';

/** Crea gli utenti di prova via admin API: i sign-up pubblici sono chiusi. */
export default async function globalSetup(): Promise<void> {
  for (const person of [CONSULTANT, OUTSIDER]) await createUser(person);
}

async function createUser(person: { email: string; password: string }): Promise<void> {
  const { apiUrl, secretKey } = localSupabase();
  const response = await fetch(`${apiUrl}/auth/v1/admin/users`, {
    method: 'POST',
    headers: { apikey: secretKey, Authorization: `Bearer ${secretKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...person, email_confirm: true }),
  });
  // 422 = esiste gia' da un giro precedente: va bene.
  if (!response.ok && response.status !== 422) {
    throw new Error(`creazione utente di prova fallita: HTTP ${response.status}`);
  }
}

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Field, FormDialog, VocabularySelect } from "@/components/form";
import { Input } from "@/ui/input";
import { CLIENT_STATUSES, type ClientDraft } from "@/contracts/workspace";
import { httpErrorMessage } from "@/lib/http";
import { useCreateClientMutation, useUpdateClientMutation } from "../api";
import type { Client } from "../types";

const EMPTY: ClientDraft = {
  name: "",
  sector: "",
  status: "Prospect",
  owner: "",
  contact: "",
};

function draftFrom(client: Client | null): ClientDraft {
  if (!client) return EMPTY;
  return {
    name: client.name,
    sector: client.sector,
    status: client.status,
    owner: client.owner,
    contact: client.contact,
  };
}

type ClientFormDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** `null` crea, un cliente modifica quel record. */
  client: Client | null;
};

/**
 * Anagrafica cliente modificabile a mano.
 *
 * Gli stessi campi che l'agente scrive dalla chat, sullo stesso record: il
 * consulente non deve chiedere a un agente il permesso di correggere un settore
 * o promuovere un prospect a cliente attivo.
 *
 * La bozza nasce dal record al montaggio e basta: chi apre il dialog gli passa
 * una `key` nuova a ogni apertura, cosi' la riapertura riparte dai dati veri
 * invece di risincronizzare lo state dentro un effetto.
 */
export function ClientFormDialog({
  open,
  onOpenChange,
  client,
}: ClientFormDialogProps): React.JSX.Element {
  const { t } = useTranslation("clients");
  const [draft, setDraft] = useState<ClientDraft>(() => draftFrom(client));
  const [error, setError] = useState<string | null>(null);

  const create = useCreateClientMutation();
  const update = useUpdateClientMutation();
  const isSubmitting = create.isPending || update.isPending;

  const set = <K extends keyof ClientDraft>(key: K, value: ClientDraft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));

  const submit = () => {
    if (!draft.name.trim()) {
      setError(t("form.error.nameRequired"));
      return;
    }
    setError(null);

    const onError = (cause: unknown) =>
      setError(httpErrorMessage(cause, t("form.error.save")));
    const onSuccess = (saved: Client) => {
      toast.success(
        client
          ? t("form.toast.updated", { name: saved.name })
          : t("form.toast.created", { name: saved.name }),
      );
      onOpenChange(false);
    };

    if (client) {
      update.mutate({ id: client.id, draft }, { onSuccess, onError });
    } else {
      create.mutate(draft, { onSuccess, onError });
    }
  };

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={client ? t("form.editTitle") : t("form.createTitle")}
      description={t("form.description")}
      submitLabel={client ? t("form.save") : t("form.create")}
      isSubmitting={isSubmitting}
      error={error}
      onSubmit={submit}
    >
      <Field label={t("form.fields.name")} required>
        {(props) => (
          <Input
            {...props}
            value={draft.name}
            autoFocus
            onChange={(event) => set("name", event.target.value)}
          />
        )}
      </Field>

      <Field label={t("form.fields.sector")}>
        {(props) => (
          <Input
            {...props}
            value={draft.sector}
            placeholder={t("form.placeholder.sector")}
            onChange={(event) => set("sector", event.target.value)}
          />
        )}
      </Field>

      <Field label={t("form.fields.status")} hint={t("form.hint.status")}>
        {(props) => (
          <VocabularySelect
            {...props}
            value={draft.status}
            onChange={(value) => set("status", value as ClientDraft["status"])}
            options={CLIENT_STATUSES.map((status) => ({
              value: status,
              label: status,
              meaning: t(`vocab.clientStatus.${status}`),
            }))}
          />
        )}
      </Field>

      <Field label={t("form.fields.owner")}>
        {(props) => (
          <Input
            {...props}
            value={draft.owner}
            placeholder={t("form.placeholder.owner")}
            onChange={(event) => set("owner", event.target.value)}
          />
        )}
      </Field>

      <Field label={t("form.fields.contact")} hint={t("form.hint.contact")}>
        {(props) => (
          <Input
            {...props}
            value={draft.contact}
            onChange={(event) => set("contact", event.target.value)}
          />
        )}
      </Field>
    </FormDialog>
  );
}

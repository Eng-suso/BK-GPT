import { useTranslation } from "react-i18next";

import { PageHeader } from "@/components/layout";
import { ServiceStatusPanel } from "@/features/status/ServiceStatusDialog";
import { SUPPORTED_LANGUAGES, type Language } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * Una sezione della pagina: titolo, a cosa serve, e il controllo.
 */
function SettingsSection({
  id,
  title,
  description,
  children,
}: {
  id: string;
  title: string;
  description: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <section
      aria-labelledby={`${id}-title`}
      className="ui-surface ui-surface-panel grid gap-4 p-5 md:grid-cols-[minmax(0,260px)_minmax(0,1fr)]"
    >
      <div>
        <h2 id={`${id}-title`} className="text-[14px] font-semibold text-foreground">
          {title}
        </h2>
        <p className="mt-1 text-[12.5px] leading-5 text-muted-foreground">{description}</p>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

/**
 * Impostazioni: solo cio' che cambia davvero qualcosa.
 *
 * Il bottone nella sidebar non portava da nessuna parte. Qui non ci sono
 * interruttori di cortesia: la lingua cambia l'interfaccia e resta scelta al
 * prossimo accesso, e lo stato del servizio dice se il backend risponde. Il
 * profilo utente arriva con l'autenticazione vera (Track B): finche' l'identita'
 * non esiste, una scheda "profilo" mostrerebbe dati che nessuno ha inserito.
 */
export function SettingsPage(): React.JSX.Element {
  const { t, i18n } = useTranslation("common");
  const current = (i18n.resolvedLanguage ?? i18n.language) as Language;

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto px-4 py-6 sm:px-7">
      <PageHeader
        breadcrumbs={[{ label: t("nav.profile") }]}
        title={t("nav.profile")}
        description={t("settings.description")}
      />

      <SettingsSection
        id="settings-language"
        title={t("settings.language.title")}
        description={t("settings.language.description")}
      >
        <fieldset>
          <legend className="sr-only">{t("settings.language.title")}</legend>
          <div className="flex flex-wrap gap-2">
            {SUPPORTED_LANGUAGES.map((lng) => {
              const checked = current === lng;
              return (
                <label
                  key={lng}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 rounded-md border border-border px-3 py-2 text-[13px] focus-within:ring-2 focus-within:ring-ring",
                    checked ? "bg-accent font-medium text-foreground" : "text-muted-foreground hover:bg-muted",
                  )}
                >
                  <input
                    type="radio"
                    name="interface-language"
                    value={lng}
                    checked={checked}
                    onChange={() => void i18n.changeLanguage(lng)}
                    className="accent-[var(--color-primary)]"
                  />
                  {t(`language.${lng}`)}
                </label>
              );
            })}
          </div>
        </fieldset>
      </SettingsSection>

      <SettingsSection
        id="settings-status"
        title={t("serviceStatus.title")}
        description={t("serviceStatus.description")}
      >
        <ServiceStatusPanel footer={StatusFooter} />
      </SettingsSection>
    </div>
  );
}

function StatusFooter({ children }: { children?: React.ReactNode }): React.JSX.Element {
  return <div className="mt-3 flex justify-end">{children}</div>;
}

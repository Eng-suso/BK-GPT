import { Check, Languages } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/ui/dropdown-menu";
import { SUPPORTED_LANGUAGES, type Language } from "@/lib/i18n";

export function LanguageMenu(): React.JSX.Element {
  const { i18n, t } = useTranslation("common");
  const current = i18n.language as Language;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={t("language.label")}
        className="ui-chrome-control"
      >
        <Languages className="size-[17px]" strokeWidth={1.7} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-32">
        {SUPPORTED_LANGUAGES.map((lng) => (
          <DropdownMenuItem
            key={lng}
            onSelect={() => void i18n.changeLanguage(lng)}
            className="text-body-sm"
            data-active={current === lng}
          >
            {t(`language.${lng}`)}
            {current === lng && <Check className="ml-auto size-4 text-primary" aria-hidden="true" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

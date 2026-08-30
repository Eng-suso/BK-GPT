import { Languages } from "lucide-react";
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
        className="grid size-[34px] place-items-center rounded-lg text-muted-foreground hover:bg-muted/60"
      >
        <Languages className="size-[17px]" strokeWidth={1.7} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-32">
        {SUPPORTED_LANGUAGES.map((lng) => (
          <DropdownMenuItem
            key={lng}
            onSelect={() => void i18n.changeLanguage(lng)}
            className="text-[13px]"
            data-active={current === lng}
          >
            {t(`language.${lng}`)}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

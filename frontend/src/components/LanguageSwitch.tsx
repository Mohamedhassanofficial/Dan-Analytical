import { Languages } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";

export default function LanguageSwitch() {
  const { locale, toggle } = useLocale();
  return (
    <button
      type="button"
      onClick={toggle}
      className="btn-ghost"
      aria-label="Toggle language"
      title={locale === "ar" ? "English" : "العربية"}
    >
      <Languages size={18} />
      <span>{locale === "ar" ? "EN" : "AR"}</span>
    </button>
  );
}

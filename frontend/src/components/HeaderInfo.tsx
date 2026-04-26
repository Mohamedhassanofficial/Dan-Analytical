import { useEffect, useRef, useState } from "react";
import { Info } from "lucide-react";
import { useLabel, useLabelsContext } from "@/contexts/LabelsContext";
import { useLocale } from "@/contexts/LocaleContext";

/**
 * Inline (i) icon next to a column header or stat card label. Shows an
 * admin-editable bilingual description from `ui_labels.description_*`.
 *
 * Per Loay slide 5 the popover lets the user pick the description language
 * inside the popover (AR ↔ EN), independent of the UI locale — so a user
 * reading the Arabic UI can still flip to English on a per-tooltip basis.
 *
 * Renders nothing when the description is null — graceful degradation while
 * descriptions are still being seeded or for keys that don't carry one
 * (identity columns like Symbol / Name).
 */
export default function HeaderInfo({
  labelKey,
  iconSize = 12,
}: {
  labelKey: string;
  /** Icon px size — small for table headers (12), larger for card corners (18). */
  iconSize?: number;
}) {
  const { labels } = useLabelsContext();
  const { locale } = useLocale();
  const label = useLabel();
  const [open, setOpen] = useState(false);
  const [lang, setLang] = useState<"ar" | "en">(locale === "ar" ? "ar" : "en");
  const wrapRef = useRef<HTMLSpanElement | null>(null);

  const entry = labels[labelKey];
  const descAr = entry?.description_ar ?? null;
  const descEn = entry?.description_en ?? null;
  const hasAny = !!(descAr || descEn);

  // Active text follows the user's toggle, with a graceful fall-back to the
  // other language when one side is missing.
  const text = lang === "ar" ? descAr ?? descEn : descEn ?? descAr;

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!hasAny) return null;

  return (
    <span ref={wrapRef} className="relative inline-flex">
      <button
        type="button"
        className="inline-flex items-center text-muted hover:text-brand-700"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        aria-label={text ?? labelKey}
      >
        <Info size={iconSize} />
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute top-full mt-1 z-30 flex max-w-xs flex-col gap-2 whitespace-normal rounded-md border border-brand-200 bg-white p-2 text-xs font-normal normal-case tracking-normal text-brand-900 shadow-md"
          style={{ insetInlineStart: 0, minWidth: "16rem" }}
        >
          <span className="inline-flex gap-1 self-start">
            <button
              type="button"
              className={
                lang === "ar"
                  ? "rounded-md bg-brand-700 px-2 py-0.5 text-[11px] font-semibold text-white"
                  : "rounded-md bg-brand-100 px-2 py-0.5 text-[11px] font-semibold text-brand-800 hover:bg-brand-200"
              }
              onClick={(e) => {
                e.stopPropagation();
                setLang("ar");
              }}
            >
              {label("tooltip.lang_ar")}
            </button>
            <button
              type="button"
              className={
                lang === "en"
                  ? "rounded-md bg-brand-700 px-2 py-0.5 text-[11px] font-semibold text-white"
                  : "rounded-md bg-brand-100 px-2 py-0.5 text-[11px] font-semibold text-brand-800 hover:bg-brand-200"
              }
              onClick={(e) => {
                e.stopPropagation();
                setLang("en");
              }}
            >
              {label("tooltip.lang_en")}
            </button>
          </span>
          <span dir={lang === "ar" ? "rtl" : "ltr"} className="leading-relaxed">
            {text}
          </span>
        </span>
      )}
    </span>
  );
}

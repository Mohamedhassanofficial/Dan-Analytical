import { useEffect, useRef, useState } from "react";
import { Info } from "lucide-react";
import { useLabelDescription } from "@/contexts/LabelsContext";

/**
 * Inline (i) icon next to a column header or stat card label. Shows an
 * admin-editable bilingual description from `ui_labels.description_*`.
 *
 * Renders nothing when the description is null — graceful degradation while
 * descriptions are still being seeded or for keys that don't carry one
 * (identity columns like Symbol / Name).
 */
export default function HeaderInfo({ labelKey }: { labelKey: string }) {
  const description = useLabelDescription();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLSpanElement | null>(null);

  const text = description(labelKey);

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

  if (!text) return null;

  return (
    <span ref={wrapRef} className="relative inline-flex">
      <button
        type="button"
        className="inline-flex items-center text-muted hover:text-brand-700"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        aria-label={text}
      >
        <Info size={12} />
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute top-full mt-1 z-30 max-w-xs whitespace-normal rounded-md border border-brand-200 bg-white p-2 text-xs font-normal normal-case tracking-normal text-brand-900 shadow-md"
          style={{ insetInlineStart: 0, minWidth: "14rem" }}
        >
          {text}
        </span>
      )}
    </span>
  );
}

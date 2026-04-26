import { Construction } from "lucide-react";
import { useLabel } from "@/contexts/LabelsContext";

/**
 * Shared "Coming soon" page used by sidebar items whose feature work is
 * out of scope for this iteration (Markets, Education, About). Keeps the
 * sidebar Links live without a 404.
 */
export default function Placeholder({
  titleKey,
  bodyKey,
}: {
  titleKey: string;
  bodyKey: string;
}) {
  const label = useLabel();
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold text-brand-900">{label(titleKey)}</h1>
      <div className="card flex flex-col items-center gap-3 py-12 text-center">
        <div className="grid h-12 w-12 place-items-center rounded-full bg-brand-100 text-brand-700">
          <Construction size={22} />
        </div>
        <p className="text-base font-medium text-brand-900">{label(bodyKey)}</p>
      </div>
    </div>
  );
}

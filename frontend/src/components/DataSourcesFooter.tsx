import { useEffect, useState } from "react";
import { Database, Link as LinkIcon } from "lucide-react";
import { StocksAPI, type DataSourceRange, type DataSourcesPayload } from "@/api/stocks";
import { useLabel } from "@/contexts/LabelsContext";

/**
 * "مصادر البيانات وفترات التحديث" footer (Loay slide).
 *
 * Three cards in a row:
 *   - تاريخ تحديث اسعار الاسهم التاريخية (3-yr stock price history)
 *   - تاريخ تحديث اسعار مؤشر القطاعات (10-yr sector indices)
 *   - اخر تاريخ لتحديث اسعار الاسهم (most recent price snapshot)
 *
 * Date ranges come live from the backend (min/max of prices_daily and
 * sector_index_daily), so they stay accurate after each refresh.
 */
export default function DataSourcesFooter() {
  const label = useLabel();
  const [data, setData] = useState<DataSourcesPayload | null>(null);

  useEffect(() => {
    StocksAPI.dataSources()
      .then(setData)
      .catch(() => setData(null));
  }, []);

  if (!data) return null;

  return (
    <div className="card p-0 overflow-hidden">
      <div className="bg-brand-700 px-4 py-2 text-center text-sm font-semibold text-white">
        {label("data_sources.title")}
      </div>
      <div className="grid grid-cols-1 items-stretch gap-3 p-3 sm:grid-cols-3">
        <SourceCard
          titleKey="data_sources.card_stock_prices_title"
          range={data.stock_prices}
        />
        <SourceCard
          titleKey="data_sources.card_sector_indices_title"
          range={data.sector_indices}
        />
        <SourceCard
          titleKey="data_sources.card_last_update_title"
          range={data.last_update}
        />
      </div>
    </div>
  );
}

function SourceCard({
  titleKey,
  range,
}: {
  titleKey: string;
  range: DataSourceRange;
}) {
  const label = useLabel();
  const fromText = range.date_from ?? "—";
  const toText = range.date_to ?? "—";

  return (
    <div className="flex h-full flex-col rounded-lg border border-brand-200 bg-brand-50 p-3 text-sm">
      {/* Title — fixed three-line slot so all three cards align even when
          one title (sector indices) wraps deeper than the other two. */}
      <div className="line-clamp-3 min-h-[3.6rem] text-sm font-semibold leading-snug text-brand-900">
        {label(titleKey)}
      </div>

      {/* Dates — single nowrap line with tabular numerals so the digits
          line up across cards and don't break in the middle of a date. */}
      <div className="mt-2 whitespace-nowrap text-xs tabular-nums text-brand-800">
        {label("data_sources.from_to", { from: fromText, to: toText })}
      </div>

      {/* Source row — mt-auto pushes the pill to the bottom of the
          flex column so every card's source row sits on the same line. */}
      <div className="mt-auto flex items-center justify-between gap-2 rounded-md border border-brand-200 bg-white px-2 py-1.5">
        <div className="inline-flex items-center gap-1.5 text-xs text-brand-900">
          <Database size={14} className="text-brand-700" />
          <span className="font-semibold">{label("data_sources.data_source_label")}</span>
        </div>
        {range.source_url ? (
          <a
            href={range.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:text-brand-900"
          >
            <LinkIcon size={12} />
            {range.source_name}
          </a>
        ) : (
          <span className="text-xs font-semibold text-brand-900">{range.source_name}</span>
        )}
      </div>
    </div>
  );
}

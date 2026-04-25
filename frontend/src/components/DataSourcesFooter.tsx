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
      <div className="grid grid-cols-1 gap-3 p-3 sm:grid-cols-3">
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
    <div className="rounded-lg border border-brand-200 bg-brand-50 p-3 text-sm">
      <div className="font-semibold text-brand-900 leading-snug">
        {label(titleKey)}
      </div>
      <div className="mt-1 text-xs text-brand-800">
        {label("data_sources.from_to", { from: fromText, to: toText })}
      </div>
      <div className="mt-3 flex items-center justify-between rounded-md border border-brand-200 bg-white px-2 py-1.5">
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

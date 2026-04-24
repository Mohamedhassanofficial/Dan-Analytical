import { useTranslation } from "react-i18next";

/**
 * Saved-portfolio management. Full create/edit UI lands in the next
 * frontend iteration (drag-and-drop holdings editor). For now this is a
 * placeholder that points users to the Optimize page.
 */
export default function PortfolioListPage() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold text-navy">{t("nav.portfolios")}</h1>
      <div className="card text-muted">
        Saved-portfolio management will land in the next iteration.
      </div>
    </div>
  );
}

import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import { useLabel } from "@/contexts/LabelsContext";

export default function Layout() {
  const label = useLabel();
  return (
    <div className="flex min-h-screen flex-col bg-surface text-ink">
      <Sidebar />
      <div className="flex min-h-screen flex-1 flex-col lg:ps-64">
        <TopBar />
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>
        <footer className="border-t border-brand-200 bg-white">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-3 text-xs text-muted sm:px-6 lg:px-8">
            <span className="font-semibold text-brand-900">
              {label("home.footer_version")}
            </span>
            <span>{label("home.quick_links")}</span>
          </div>
        </footer>
      </div>
    </div>
  );
}

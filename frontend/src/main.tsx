import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./i18n";
import "./index.css";
import App from "./App";
import { AuthProvider } from "@/contexts/AuthContext";
import { LabelsProvider } from "@/contexts/LabelsContext";
import { LocaleProvider } from "@/contexts/LocaleContext";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <LocaleProvider>
      <AuthProvider>
        <LabelsProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </LabelsProvider>
      </AuthProvider>
    </LocaleProvider>
  </StrictMode>,
);

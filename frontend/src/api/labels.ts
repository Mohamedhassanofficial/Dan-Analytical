import { api } from "./client";

export interface UiLabel {
  key: string;
  label_ar: string;
  label_en: string;
  description_ar: string | null;
  description_en: string | null;
  context: string | null;
  updated_at: string;
}

export const LabelsAPI = {
  list: (context?: string) =>
    api<UiLabel[]>(context ? `/ui-labels?context=${encodeURIComponent(context)}` : "/ui-labels"),

  update: (key: string, payload: Partial<Pick<UiLabel, "label_ar" | "label_en" | "description_ar" | "description_en">>) =>
    api<UiLabel>(`/admin/ui-labels/${encodeURIComponent(key)}`, {
      method: "PUT",
      body: payload,
    }),
};

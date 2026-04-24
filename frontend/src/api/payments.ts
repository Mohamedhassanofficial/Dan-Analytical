import { api } from "./client";

export interface CheckoutOut {
  gateway: string;
  gateway_reference: string;
  redirect_url: string;
  merchant_reference: string;
  amount: string; // Decimal serialized
  currency: string;
}

export interface SubscriptionOut {
  id: number;
  gateway: string;
  gateway_transaction_id: string | null;
  amount: string;
  currency: string;
  status: "pending" | "completed" | "failed" | "refunded";
  starts_at: string | null;
  expires_at: string | null;
  created_at: string;
}

export const PaymentsAPI = {
  subscribe: (returnUrl: string) =>
    api<CheckoutOut>("/payments/subscribe", {
      method: "POST",
      body: { return_url: returnUrl },
    }),

  subscriptions: () => api<SubscriptionOut[]>("/payments/subscriptions"),
};

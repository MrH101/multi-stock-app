import { api } from "@/shared/api/http";
import { useSession } from "@/shared/auth/session";

export type Method = "ecocash" | "onemoney" | "innbucks" | "paynow_web" | "bank_transfer";
export type PayStatus = "CREATED" | "PENDING" | "AWAITING_CONFIRMATION" | "PAID" | "FAILED" | "CANCELLED" | "REJECTED" | "DISPUTED" | "REFUNDED";

export interface Proof {
  id: number;
  filename: string;
  content_type: string;
  size: number;
  bank_reference: string | null;
  uploaded_by: string;
  reviewed_by: string | null;
  review_note: string | null;
  created_at: string;
}

export interface Payment {
  id: number;
  reference: string;
  order_id: number;
  order_number: string;
  amount: string;
  currency: string;
  method: Method;
  status: PayStatus;
  phone: string | null;
  provider_reference: string | null;
  redirect_url: string | null;
  instructions: string | null;
  innbucks_code: string | null;
  innbucks_expires: string | null;
  paid_at: string | null;
  created_by_name: string;
  note: string | null;
  error: string | null;
  created_at: string;
  proofs: Proof[];
}

export interface PaymentOptions {
  order_number: string;
  amount: string;
  currency: string;
  payment_status: string | null;
  methods: Method[];
  bank: { bank_name: string | null; bank_account_name: string | null; bank_account_number: string | null; bank_branch: string | null; payment_instructions: string | null } | null;
  reason: string | null;
}

export interface MerchantAccount {
  currency: string;
  paynow_enabled: boolean;
  paynow_integration_id: string | null;
  paynow_integration_key_masked: string | null;
  bank_name: string | null;
  bank_account_name: string | null;
  bank_account_number: string | null;
  bank_branch: string | null;
  payment_instructions: string | null;
}

export type MerchantInput = Omit<MerchantAccount, "currency" | "paynow_integration_key_masked"> & { paynow_integration_key?: string };

export const METHOD_LABEL: Record<Method, string> = {
  ecocash: "EcoCash",
  onemoney: "OneMoney",
  innbucks: "InnBucks",
  paynow_web: "Card / ZimSwitch",
  bank_transfer: "Bank transfer",
};

export const PAY_STATUS: Record<PayStatus, { label: string; color: string }> = {
  CREATED: { label: "Starting", color: "gray" },
  PENDING: { label: "Waiting for approval", color: "blue" },
  AWAITING_CONFIRMATION: { label: "Supplier to confirm", color: "yellow" },
  PAID: { label: "Paid", color: "green" },
  FAILED: { label: "Failed", color: "red" },
  CANCELLED: { label: "Cancelled", color: "gray" },
  REJECTED: { label: "Proof rejected", color: "red" },
  DISPUTED: { label: "Needs checking", color: "orange" },
  REFUNDED: { label: "Refunded", color: "grape" },
};

export const paymentsApi = {
  options: (orderNumber: string) => api<PaymentOptions>("payments", `/orders/${orderNumber}/options`),
  list: (orderNumber: string) => api<Payment[]>("payments", "/payments", { query: { order_number: orderNumber } }),
  start: (order_number: string, method: Method, phone?: string) =>
    api<Payment>("payments", "/payments", { method: "POST", body: { order_number, method, phone } }),
  refresh: (id: number) => api<Payment>("payments", `/payments/${id}/refresh`, { method: "POST" }),
  uploadProof: (order_number: string, file: File, bank_reference?: string) => {
    const form = new FormData();
    form.append("order_number", order_number);
    if (bank_reference) form.append("bank_reference", bank_reference);
    form.append("file", file);
    return api<Payment>("payments", "/payments/proof", { method: "POST", form });
  },
  review: (id: number, accept: boolean, note?: string) =>
    api<Payment>("payments", `/payments/${id}/review`, { method: "POST", body: { accept, note } }),
  openProof: async (paymentId: number, proofId: number) => {
    const token = useSession.getState().accessToken;
    const res = await fetch(`/api/payments/payments/${paymentId}/proofs/${proofId}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!res.ok) throw new Error("Could not open the file");
    window.open(URL.createObjectURL(await res.blob()), "_blank", "noopener");
  },
  accounts: () => api<MerchantAccount[]>("payments", "/merchant-accounts"),
  saveAccount: (currency: string, body: MerchantInput) => api<MerchantAccount>("payments", `/merchant-accounts/${currency}`, { method: "PUT", body }),
};

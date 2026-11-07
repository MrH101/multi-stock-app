import { api, type Page } from "@/shared/api/http";

export type OrderStatus = "SUBMITTED" | "ACCEPTED" | "REJECTED" | "DISPATCHED" | "DELIVERED" | "CANCELLED";
export type PaymentMethod = "CASH_ON_DELIVERY" | "BANK_TRANSFER" | "ON_ACCOUNT" | "MOBILE_MONEY";

export const PAYMENT_METHODS: Record<PaymentMethod, string> = {
  CASH_ON_DELIVERY: "Cash on delivery",
  BANK_TRANSFER: "Bank transfer",
  ON_ACCOUNT: "On account (credit terms)",
  MOBILE_MONEY: "Mobile money",
};

export interface OrderSummary {
  id: number;
  order_number: string;
  pharmacy_org_id: number;
  pharmacy_name: string;
  supplier_org_id: number;
  supplier_name: string;
  status: OrderStatus;
  currency: string;
  subtotal: string;
  item_count: number;
  created_by_name: string;
  created_at: string;
  updated_at: string;
}

export interface Order extends OrderSummary {
  payment_method: PaymentMethod;
  delivery_address: string;
  contact_name: string;
  contact_phone: string;
  notes: string | null;
  lines: {
    id: number;
    product_id: number;
    product_name: string;
    generic_name: string | null;
    strength: string | null;
    pack_size: string | null;
    quantity: number;
    unit_price: string;
    line_total: string;
    schedule: string | null;
    mcaz_registration_number: string | null;
    allocations: { batch_number: string; expiry_date: string; quantity: number }[];
  }[];
  history: { status: OrderStatus; note: string | null; actor_name: string; actor_org_name: string; at: string }[];
  allowed_transitions: OrderStatus[];
}

export interface Budget {
  period: string;
  amount: string;
  currency: string;
  committed: string;
  remaining: string;
  percent_used: number;
  is_set: boolean;
}

export interface DashboardSummary {
  counts: Record<OrderStatus, number>;
  open_orders: number;
  month_total: string;
  currency: string;
  monthly: { month: string; total: string }[];
  top_products: { product_id: number; product_name: string; quantity: number; total: string }[];
}

export interface CheckoutInput {
  lines: { product_id: number; quantity: number }[];
  delivery_address: string;
  contact_name: string;
  contact_phone: string;
  payment_method: PaymentMethod;
  notes?: string;
  idempotency_key: string;
}

export const ordersApi = {
  list: (query: { status?: OrderStatus[]; q?: string; page?: number }) => api<Page<OrderSummary>>("orders", "/orders", { query }),
  get: (id: number) => api<Order>("orders", `/orders/${id}`),
  checkout: (body: CheckoutInput) => api<Order[]>("orders", "/orders/checkout", { method: "POST", body }),
  changeStatus: (id: number, status: OrderStatus, note?: string) =>
    api<Order>("orders", `/orders/${id}/status`, { method: "POST", body: { status, note } }),
  summary: () => api<DashboardSummary>("orders", "/orders/summary"),
  budget: () => api<Budget>("orders", "/budget"),
  setBudget: (amount: number, currency: string) => api<Budget>("orders", "/budget", { method: "PUT", body: { amount, currency } }),
};

import { api, download, type Page } from "@/shared/api/http";

export interface Product {
  id: number;
  supplier_org_id: number;
  supplier_name: string;
  sku: string | null;
  name: string;
  generic_name: string | null;
  strength: string | null;
  dosage_form: string;
  pack_size: string | null;
  manufacturer: string | null;
  schedule: string;
  mcaz_registration_number: string | null;
  unit_price: string;
  currency: string;
  description: string | null;
  reorder_level: number;
  is_active: boolean;
  created_at: string;
  stock_available: number;
  nearest_expiry: string | null;
}

export interface ProductDetail extends Product {
  batches: { batch_number: string; expiry_date: string; quantity_available: number }[];
}

export interface Batch {
  id: number;
  product_id: number;
  batch_number: string;
  expiry_date: string;
  quantity_available: number;
  quantity_reserved: number;
}

export interface Movement {
  id: number;
  batch_id: number;
  change: number;
  reason: string;
  reference: string | null;
  note: string | null;
  created_at: string;
}

export interface InventoryAlerts {
  expiring: { batch_id: number; product_id: number; product_name: string; batch_number: string; expiry_date: string; days_to_expiry: number; quantity_available: number }[];
  expired: InventoryAlerts["expiring"];
  low_stock: { product_id: number; product_name: string; stock_available: number; reorder_level: number }[];
}

export interface ImportReport {
  committed: boolean;
  summary: { total: number; create: number; update: number; unchanged: number; error: number; batches_added: number };
  columns: Record<string, string>;
  ignored_columns: string[];
  rows: { row: number; sku: string | null; name: string | null; action: "create" | "update" | "unchanged" | "error"; messages: string[]; batch: "added" | "exists" | null }[];
}

export type ProductInput = Omit<Product, "id" | "supplier_org_id" | "supplier_name" | "is_active" | "created_at" | "stock_available" | "nearest_expiry">;

export const catalogApi = {
  search: (query: { q?: string; dosage_form?: string | null; supplier_org_id?: number; in_stock?: boolean; page?: number; page_size?: number }) =>
    api<Page<Product>>("catalog", "/products", { query }),
  product: (id: number) => api<ProductDetail>("catalog", `/products/${id}`),
  myProducts: (query: { q?: string; page?: number }) => api<Page<Product>>("catalog", "/supplier/products", { query: { ...query, page_size: 100 } }),
  importPriceList: (file: File, commit: boolean) => {
    const form = new FormData();
    form.append("file", file);
    return api<ImportReport>("catalog", "/supplier/imports", { method: "POST", form, query: { commit } });
  },
  importTemplate: () => download("catalog", "/supplier/imports/template.csv", "multistock-price-list-template.csv"),
  createProduct: (body: ProductInput) => api<Product>("catalog", "/products", { method: "POST", body }),
  updateProduct: (id: number, body: Partial<ProductInput> & { is_active?: boolean }) =>
    api<Product>("catalog", `/products/${id}`, { method: "PATCH", body }),
  batches: (productId: number) => api<Batch[]>("catalog", `/products/${productId}/batches`),
  receiveBatch: (productId: number, body: { batch_number: string; expiry_date: string; quantity: number }) =>
    api<Batch>("catalog", `/products/${productId}/batches`, { method: "POST", body }),
  adjustBatch: (batchId: number, body: { change: number; reason: string; note?: string }) =>
    api<Batch>("catalog", `/batches/${batchId}/adjustments`, { method: "POST", body }),
  movements: (batchId: number) => api<Movement[]>("catalog", `/batches/${batchId}/movements`),
  alerts: (days = 90) => api<InventoryAlerts>("catalog", "/inventory/alerts", { query: { days } }),
};

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Product } from "@/modules/catalog/api";

export interface CartLine {
  product: Pick<Product, "id" | "name" | "generic_name" | "strength" | "pack_size" | "unit_price" | "currency" | "supplier_org_id" | "supplier_name" | "stock_available">;
  quantity: number;
}

interface CartState {
  lines: Record<number, CartLine>;
  /** stable per-cart key so a double-clicked "Place order" never creates duplicate orders */
  checkoutKey: string;
  add: (product: CartLine["product"], quantity: number) => void;
  setQuantity: (productId: number, quantity: number) => void;
  remove: (productId: number) => void;
  clear: () => void;
}

const newKey = () => crypto.randomUUID();

export const useCart = create<CartState>()(
  persist(
    (set) => ({
      lines: {},
      checkoutKey: newKey(),
      add: (product, quantity) =>
        set((s) => {
          const existing = s.lines[product.id]?.quantity ?? 0;
          return { lines: { ...s.lines, [product.id]: { product, quantity: existing + quantity } } };
        }),
      setQuantity: (productId, quantity) =>
        set((s) => (s.lines[productId] ? { lines: { ...s.lines, [productId]: { ...s.lines[productId], quantity } } } : s)),
      remove: (productId) =>
        set((s) => {
          const { [productId]: _removed, ...rest } = s.lines;
          return { lines: rest };
        }),
      clear: () => set({ lines: {}, checkoutKey: newKey() }),
    }),
    { name: "multistock-cart" },
  ),
);

export const cartCount = (lines: Record<number, CartLine>) => Object.keys(lines).length;

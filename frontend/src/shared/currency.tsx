import { SegmentedControl, Text, Tooltip } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { ordersApi, type Rates } from "@/modules/orders/api";
import { useSession } from "@/shared/auth/session";
import { CURRENCY_LABEL, date, money } from "@/shared/format";

/** The currency the user prefers to *see* amounts in. Prices and orders keep their own currency. */
export const useDisplayCurrency = create<{ currency: string; set: (c: string) => void }>()(
  persist((set) => ({ currency: "USD", set: (currency) => set({ currency }) }), { name: "multistock-display-currency" }),
);

export function useRates() {
  const token = useSession((s) => s.accessToken);
  return useQuery({ queryKey: ["fx"], queryFn: ordersApi.rates, enabled: !!token, staleTime: 10 * 60_000 });
}

export function convert(amount: number | string, from: string, to: string, rates?: Record<string, string> | null): number | null {
  if (from === to) return Number(amount);
  const r = rates ?? {};
  if (!r[from] || !r[to]) return null;
  return (Number(amount) / Number(r[from])) * Number(r[to]);
}

/** Effective display currency: falls back to the native one when no rate is known. */
export function useDisplay() {
  const { currency } = useDisplayCurrency();
  const rates = useRates().data;
  return { currency, rates: rates?.rates ?? null, info: rates };
}

/** Shows an amount in its own currency, plus the equivalent in the user's display currency. */
export function Money({ amount, currency, rates, size = "sm", fw = 600, inline = false }: {
  amount: number | string; currency: string; rates?: Record<string, string> | null; size?: string; fw?: number; inline?: boolean;
}) {
  const display = useDisplay();
  const use = rates ?? display.rates;
  const alt = display.currency !== currency ? convert(amount, currency, display.currency, use) : null;
  return (
    <span style={{ display: inline ? "inline" : "block" }}>
      <Text span={inline} size={size} fw={fw}>{money(amount, currency)}</Text>
      {alt !== null && (
        <Text span={inline} size="xs" c="dimmed" ml={inline ? 6 : 0}>≈ {money(alt, display.currency)}</Text>
      )}
    </span>
  );
}

export function rateLabel(info?: Rates | null, currency = "ZWG") {
  if (!info?.rates[currency]) return null;
  return `1 USD = ${Number(info.rates[currency]).toLocaleString("en-ZW", { maximumFractionDigits: 4 })} ${CURRENCY_LABEL[currency] ?? currency}` +
    (info.as_of[currency] ? ` · ${date(info.as_of[currency])}` : "");
}

/** Header switch between USD and ZiG; hidden until a ZiG rate exists. */
export function CurrencySwitch() {
  const { currency, set } = useDisplayCurrency();
  const rates = useRates().data;
  if (!rates?.rates.ZWG) return null;
  return (
    <Tooltip label={`Show amounts in… (${rateLabel(rates)})`}>
      <SegmentedControl size="xs" value={currency} onChange={set} data={[{ value: "USD", label: "USD" }, { value: "ZWG", label: "ZiG" }]} aria-label="Display currency" />
    </Tooltip>
  );
}

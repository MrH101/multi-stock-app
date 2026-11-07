import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";

dayjs.extend(relativeTime);

export function money(amount: string | number, currency = "USD") {
  return new Intl.NumberFormat("en-ZW", { style: "currency", currency }).format(Number(amount));
}

export const date = (d: string | null | undefined) => (d ? dayjs(d).format("D MMM YYYY") : "—");
export const dateTime = (d: string) => dayjs(d).format("D MMM YYYY, HH:mm");
export const fromNow = (d: string) => dayjs(d).fromNow();
export const daysUntil = (d: string) => dayjs(d).startOf("day").diff(dayjs().startOf("day"), "day");

export const DOSAGE_FORMS: Record<string, string> = {
  TABLET: "Tablet",
  CAPSULE: "Capsule",
  SYRUP: "Syrup",
  SUSPENSION: "Suspension",
  INJECTION_AMPOULE: "Injection (ampoule)",
  INJECTION_VIAL: "Injection (vial)",
  PEN: "Pen",
  CREAM_OINTMENT: "Cream / ointment",
  DROPS: "Drops",
  INHALER: "Inhaler",
  SUPPOSITORY: "Suppository",
  PESSARY: "Pessary",
  SURGICAL: "Surgical",
  OTHER: "Other",
};

export const SCHEDULES: Record<string, string> = {
  OTC: "OTC (general sale)",
  P: "Pharmacy only",
  PP: "Pharmacist-initiated",
  PRESCRIPTION: "Prescription only",
  CONTROLLED: "Controlled drug",
};

export const options = (m: Record<string, string>) => Object.entries(m).map(([value, label]) => ({ value, label }));

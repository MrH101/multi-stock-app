import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";

dayjs.extend(relativeTime);

export function money(amount: string | number, currency = "USD") {
  // ZiG (ISO code ZWG) is newer than most browsers' currency data, so label it the way people write it.
  if (currency === "ZWG")
    return `ZiG ${new Intl.NumberFormat("en-ZW", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(amount))}`;
  return new Intl.NumberFormat("en-ZW", { style: "currency", currency }).format(Number(amount));
}

export const CURRENCY_LABEL: Record<string, string> = { USD: "USD", ZWG: "ZiG", ZAR: "ZAR" };

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

/** MCAZ legal supply categories. */
export const SCHEDULES: Record<string, string> = {
  PP: "PP · Prescription Preparation",
  PIM: "PIM · Pharmacist-Initiated Medicine",
  P: "P · Pharmacy Medicine",
  HR: "HR · Household Remedy",
  CD: "CD · Controlled / dangerous drug",
  NON_MEDICINE: "Non-medicine (surgical, sundries)",
};

/** Short badge for categories pharmacists must notice before ordering or dispensing. */
export const SCHEDULE_BADGE: Record<string, { label: string; color: string }> = {
  PP: { label: "Prescription (PP)", color: "grape" },
  PIM: { label: "Pharmacist-initiated", color: "indigo" },
  CD: { label: "Controlled drug", color: "red" },
};

export const options = (m: Record<string, string>) => Object.entries(m).map(([value, label]) => ({ value, label }));

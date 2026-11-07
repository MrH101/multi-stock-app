import { Button, Grid, Group, NumberInput, Select, Stack, Textarea, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { DOSAGE_FORMS, SCHEDULES, options } from "@/shared/format";
import { ErrorNotice } from "@/shared/ui";
import type { Product, ProductInput } from "./api";

const EMPTY: ProductInput = {
  sku: "", name: "", generic_name: "", strength: "", dosage_form: "TABLET", pack_size: "", manufacturer: "",
  schedule: "P", mcaz_registration_number: "", unit_price: "", currency: "USD", description: "", reorder_level: 0,
};

export function ProductForm({ initial, onSubmit, submitting, error, submitLabel = "Save product" }: {
  initial?: Product; onSubmit: (v: ProductInput) => void; submitting: boolean; error: unknown; submitLabel?: string;
}) {
  const form = useForm<ProductInput>({
    initialValues: initial ? { ...EMPTY, ...Object.fromEntries(Object.entries(initial).map(([k, v]) => [k, v ?? ""])) } as ProductInput : EMPTY,
    validate: {
      name: (v) => (v.trim().length >= 2 ? null : "Required"),
      unit_price: (v) => (Number(v) > 0 ? null : "Enter a price above zero"),
    },
  });
  const clean = (v: ProductInput): ProductInput => {
    const out = { ...v, unit_price: String(Number(v.unit_price).toFixed(2)), reorder_level: Number(v.reorder_level) || 0 };
    for (const k of ["sku", "generic_name", "strength", "pack_size", "manufacturer", "description", "mcaz_registration_number"] as const) if (!out[k]) out[k] = null;
    return out;
  };

  return (
    <form onSubmit={form.onSubmit((v) => onSubmit(clean(v)))}>
      <Stack>
        {error ? <ErrorNotice error={error} title="Could not save" /> : null}
        <Grid>
          <Grid.Col span={{ base: 12, sm: 6 }}><TextInput label="Brand / trade name" required {...form.getInputProps("name")} /></Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}><TextInput label="Generic name (INN)" placeholder="e.g. Amoxicillin" {...form.getInputProps("generic_name")} /></Grid.Col>
          <Grid.Col span={{ base: 6, sm: 4 }}><TextInput label="Strength" placeholder="500mg" {...form.getInputProps("strength")} /></Grid.Col>
          <Grid.Col span={{ base: 6, sm: 4 }}><Select label="Dosage form" data={options(DOSAGE_FORMS)} allowDeselect={false} {...form.getInputProps("dosage_form")} /></Grid.Col>
          <Grid.Col span={{ base: 6, sm: 4 }}><TextInput label="Pack size" placeholder="10 x 10" {...form.getInputProps("pack_size")} /></Grid.Col>
          <Grid.Col span={{ base: 6, sm: 6 }}><TextInput label="Manufacturer" {...form.getInputProps("manufacturer")} /></Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}><Select label="MCAZ category" data={options(SCHEDULES)} allowDeselect={false} {...form.getInputProps("schedule")} /></Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}><TextInput label="MCAZ registration no." placeholder="As on the MCAZ register" description="Lets pharmacies confirm the product is registered" {...form.getInputProps("mcaz_registration_number")} /></Grid.Col>
          <Grid.Col span={{ base: 6, sm: 4 }}><NumberInput label="Unit price" required min={0} decimalScale={2} fixedDecimalScale {...form.getInputProps("unit_price")} /></Grid.Col>
          <Grid.Col span={{ base: 6, sm: 2 }}><Select label="Currency" data={["USD", "ZWG", "ZAR"]} allowDeselect={false} {...form.getInputProps("currency")} /></Grid.Col>
          <Grid.Col span={{ base: 6, sm: 3 }}><TextInput label="Your SKU / code" {...form.getInputProps("sku")} /></Grid.Col>
          <Grid.Col span={{ base: 6, sm: 3 }}><NumberInput label="Reorder level" description="Alert when stock falls to this" min={0} {...form.getInputProps("reorder_level")} /></Grid.Col>
          <Grid.Col span={12}><Textarea label="Description / notes for pharmacies" autosize minRows={2} {...form.getInputProps("description")} /></Grid.Col>
        </Grid>
        <Group justify="flex-end"><Button type="submit" loading={submitting}>{submitLabel}</Button></Group>
      </Stack>
    </form>
  );
}

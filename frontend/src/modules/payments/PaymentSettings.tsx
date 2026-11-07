import { Badge, Button, Card, Divider, Grid, Group, PasswordInput, SegmentedControl, Stack, Switch, Text, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { CURRENCY_LABEL } from "@/shared/format";
import { ErrorNotice } from "@/shared/ui";
import { paymentsApi, type MerchantAccount, type MerchantInput } from "./api";

const EMPTY: MerchantInput = { paynow_enabled: false, paynow_integration_id: "", paynow_integration_key: "", bank_name: "", bank_account_name: "", bank_account_number: "", bank_branch: "", payment_instructions: "" };

/** Supplier settings: where pharmacies' payments go, per currency. */
export function PaymentSettings() {
  const qc = useQueryClient();
  const accounts = useQuery({ queryKey: ["merchant-accounts"], queryFn: paymentsApi.accounts });
  const [currency, setCurrency] = useState("USD");
  const current = accounts.data?.find((a) => a.currency === currency);
  const form = useForm<MerchantInput>({ initialValues: EMPTY });
  useEffect(() => {
    if (!current) return;
    const { currency: _c, paynow_integration_key_masked: _k, ...rest } = current as MerchantAccount;
    form.setValues({ ...EMPTY, ...Object.fromEntries(Object.entries(rest).map(([k, v]) => [k, v ?? ""])), paynow_integration_key: "" });
  }, [current?.currency, accounts.dataUpdatedAt]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useMutation({
    mutationFn: (v: MerchantInput) => paymentsApi.saveAccount(currency, {
      ...v, paynow_integration_key: v.paynow_integration_key || undefined,
      ...Object.fromEntries(Object.entries(v).filter(([k]) => k !== "paynow_enabled").map(([k, val]) => [k, val === "" ? null : val])),
    } as MerchantInput),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["merchant-accounts"] });
      notifications.show({ color: "teal", message: `${CURRENCY_LABEL[currency]} payment details saved` });
    },
  });

  return (
    <Card>
      <Group justify="space-between" mb="xs">
        <Title order={4}>Getting paid</Title>
        <SegmentedControl size="xs" value={currency} onChange={setCurrency} data={[{ value: "USD", label: "USD" }, { value: "ZWG", label: "ZiG" }]} />
      </Group>
      <Text size="sm" c="dimmed" mb="md">
        Pharmacies pay you directly. Connect your Paynow account to accept EcoCash, OneMoney, InnBucks and cards, and add bank details for transfers.
        Paynow gives you a separate integration for each currency (Paynow → Settings → Integrations).
      </Text>
      <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
        <Stack>
          {save.error && <ErrorNotice error={save.error} title="Not saved" />}
          <Switch label={`Accept Paynow payments in ${CURRENCY_LABEL[currency]}`} {...form.getInputProps("paynow_enabled", { type: "checkbox" })} />
          <Grid>
            <Grid.Col span={{ base: 12, sm: 5 }}><TextInput label="Integration ID" inputMode="numeric" {...form.getInputProps("paynow_integration_id")} /></Grid.Col>
            <Grid.Col span={{ base: 12, sm: 7 }}>
              <PasswordInput label="Integration key" placeholder={current?.paynow_integration_key_masked ?? "Paste the key from Paynow"}
                description={current?.paynow_integration_key_masked ? "Stored encrypted. Leave empty to keep it." : "Stored encrypted, never shown again."}
                {...form.getInputProps("paynow_integration_key")} />
            </Grid.Col>
          </Grid>
          <Divider label="Bank transfer" labelPosition="left" />
          <Grid>
            <Grid.Col span={{ base: 12, sm: 6 }}><TextInput label="Bank" placeholder="e.g. CBZ" {...form.getInputProps("bank_name")} /></Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6 }}><TextInput label="Branch" {...form.getInputProps("bank_branch")} /></Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6 }}><TextInput label="Account name" {...form.getInputProps("bank_account_name")} /></Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6 }}><TextInput label="Account number" {...form.getInputProps("bank_account_number")} /></Grid.Col>
            <Grid.Col span={12}><TextInput label="Instructions for pharmacies (optional)" placeholder="e.g. Send POP to accounts@…" {...form.getInputProps("payment_instructions")} /></Grid.Col>
          </Grid>
          <Group justify="space-between">
            {current?.paynow_enabled ? <Badge color="green" variant="light">Paynow on</Badge> : <Badge color="gray" variant="light">Paynow off</Badge>}
            <Button type="submit" loading={save.isPending}>Save {CURRENCY_LABEL[currency]} details</Button>
          </Group>
        </Stack>
      </form>
    </Card>
  );
}

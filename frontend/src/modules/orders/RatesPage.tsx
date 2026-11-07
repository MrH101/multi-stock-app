import { Button, Card, Grid, Group, NumberInput, Stack, Table, Text, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { rateLabel } from "@/shared/currency";
import { CURRENCY_LABEL, date, dateTime } from "@/shared/format";
import { ErrorNotice, PageHeader } from "@/shared/ui";
import { ordersApi } from "./api";

export default function RatesPage() {
  const qc = useQueryClient();
  const rates = useQuery({ queryKey: ["fx"], queryFn: ordersApi.rates });
  const history = useQuery({ queryKey: ["fx", "history"], queryFn: ordersApi.rateHistory });
  const [zwg, setZwg] = useState<number | string>("");
  const [zar, setZar] = useState<number | string>("");
  const [source, setSource] = useState("RBZ interbank rate");
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, number> = {};
      if (Number(zwg) > 0) body.ZWG = Number(zwg);
      if (Number(zar) > 0) body.ZAR = Number(zar);
      return ordersApi.setRates(body, source);
    },
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["fx"] });
      notifications.show({ color: "teal", title: "Rates updated", message: rateLabel(r) ?? "Saved" });
      setZwg("");
      setZar("");
    },
  });
  const r = rates.data;

  return (
    <>
      <PageHeader title="Exchange rates" description="Rates used to show USD/ZiG equivalents and to count budgets and reports across currencies. Each order keeps the rate in force when it was placed." />
      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Card>
            <Text fw={600} mb="sm">Today's rates (per 1 USD)</Text>
            {rates.error && <ErrorNotice error={rates.error} />}
            <Stack gap="xs" mb="lg">
              {["ZWG", "ZAR"].map((c) => (
                <Group key={c} justify="space-between">
                  <Text>{CURRENCY_LABEL[c]}</Text>
                  <Text fw={600}>{r?.rates[c] ? `${Number(r.rates[c]).toLocaleString("en-ZW", { maximumFractionDigits: 4 })} · ${date(r.as_of[c])}` : <Text span c="orange">not set</Text>}</Text>
                </Group>
              ))}
            </Stack>
            <Stack>
              {save.error && <ErrorNotice error={save.error} title="Not saved" />}
              <NumberInput label="ZiG per 1 USD" placeholder={r?.rates.ZWG ?? "e.g. 26.80"} min={0} decimalScale={6} value={zwg} onChange={setZwg} />
              <NumberInput label="ZAR per 1 USD (optional)" placeholder={r?.rates.ZAR ?? "e.g. 18.20"} min={0} decimalScale={6} value={zar} onChange={setZar} />
              <TextInput label="Source" value={source} onChange={(e) => setSource(e.currentTarget.value)} />
              <Button loading={save.isPending} disabled={!(Number(zwg) > 0 || Number(zar) > 0)} onClick={() => save.mutate()}>Save rates for today</Button>
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Card p={0}>
            <Text fw={600} p="md">History</Text>
            <Table>
              <Table.Thead><Table.Tr><Table.Th>Effective</Table.Th><Table.Th>Currency</Table.Th><Table.Th ta="right">Per USD</Table.Th><Table.Th>Source</Table.Th><Table.Th>Set by</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {history.data?.map((h, i) => (
                  <Table.Tr key={i}>
                    <Table.Td><Text size="sm">{date(h.effective_date)}</Text><Text size="xs" c="dimmed">{dateTime(h.created_at)}</Text></Table.Td>
                    <Table.Td>{CURRENCY_LABEL[h.currency] ?? h.currency}</Table.Td>
                    <Table.Td ta="right">{Number(h.per_usd).toLocaleString("en-ZW", { maximumFractionDigits: 6 })}</Table.Td>
                    <Table.Td><Text size="sm">{h.source ?? "—"}</Text></Table.Td>
                    <Table.Td><Text size="sm">{h.set_by ?? "—"}</Text></Table.Td>
                  </Table.Tr>
                ))}
                {history.data?.length === 0 && <Table.Tr><Table.Td colSpan={5}><Text size="sm" c="dimmed">No rates recorded yet.</Text></Table.Td></Table.Tr>}
              </Table.Tbody>
            </Table>
          </Card>
        </Grid.Col>
      </Grid>
    </>
  );
}

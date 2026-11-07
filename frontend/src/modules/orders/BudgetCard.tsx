import { Button, Card, Group, Modal, NumberInput, Progress, Select, Stack, Text } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useAccount } from "@/shared/auth/session";
import { money } from "@/shared/format";
import { ErrorNotice } from "@/shared/ui";
import { ordersApi } from "./api";

export function BudgetCard() {
  const { canManage } = useAccount();
  const qc = useQueryClient();
  const budget = useQuery({ queryKey: ["budget"], queryFn: ordersApi.budget });
  const [opened, { open, close }] = useDisclosure();
  const [amount, setAmount] = useState<number | string>("");
  const [currency, setCurrency] = useState("USD");
  const save = useMutation({
    mutationFn: () => ordersApi.setBudget(Number(amount), currency),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["budget"] }); close(); },
  });
  const b = budget.data;
  const pct = Math.min(100, b?.percent_used ?? 0);

  return (
    <Card h="100%">
      <Group justify="space-between" mb="xs">
        <Text fw={600}>Budget this month</Text>
        {canManage && <Button size="compact-sm" variant="subtle" onClick={() => { setAmount(b?.amount ?? ""); setCurrency(b?.currency ?? "USD"); open(); }}>{b?.is_set ? "Change" : "Set budget"}</Button>}
      </Group>
      {b && b.is_set ? (
        <Stack gap={6}>
          <Text size="xl" fw={700}>{money(b.remaining, b.currency)} <Text span size="sm" c="dimmed" fw={400}>left of {money(b.amount, b.currency)}</Text></Text>
          <Progress value={pct} color={pct >= 100 ? "red" : pct >= 80 ? "orange" : "teal"} size="lg" radius="xl" />
          <Text size="xs" c="dimmed">{money(b.committed, b.currency)} committed in open and delivered orders ({b.percent_used.toFixed(0)}%)</Text>
        </Stack>
      ) : (
        <Text size="sm" c="dimmed">No budget set. {canManage ? "Set one to get a warning before you overspend." : "Ask your manager to set one."}</Text>
      )}
      <Modal opened={opened} onClose={close} title="Monthly purchasing budget">
        <Stack>
          {save.error && <ErrorNotice error={save.error} title="Not saved" />}
          <Group grow>
            <NumberInput label="Amount" min={0} decimalScale={2} value={amount} onChange={setAmount} autoFocus />
            <Select label="Currency" data={["USD", "ZWG", "ZAR"]} value={currency} onChange={(v) => v && setCurrency(v)} allowDeselect={false} />
          </Group>
          <Group justify="flex-end"><Button variant="default" onClick={close}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate()}>Save</Button></Group>
        </Stack>
      </Modal>
    </Card>
  );
}

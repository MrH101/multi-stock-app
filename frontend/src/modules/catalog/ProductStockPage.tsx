import { Anchor, Badge, Button, Card, Grid, Group, Modal, NumberInput, Select, Stack, Switch, Table, Tabs, Text, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconArrowLeft, IconHistory, IconPackageImport } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAccount } from "@/shared/auth/session";
import { dateTime, money } from "@/shared/format";
import { ErrorNotice, ExpiryBadge, Loading, StockBadge } from "@/shared/ui";
import { catalogApi, type Batch } from "./api";
import { ProductForm } from "./ProductForm";

const REASONS = [
  { value: "ADJUSTMENT", label: "Stock count correction" },
  { value: "DAMAGED", label: "Damaged / broken" },
  { value: "EXPIRED", label: "Expired — write off" },
];

export default function ProductStockPage() {
  const productId = Number(useParams().productId);
  const qc = useQueryClient();
  const { canManage } = useAccount();
  const product = useQuery({ queryKey: ["product", productId], queryFn: () => catalogApi.product(productId) });
  const batches = useQuery({ queryKey: ["batches", productId], queryFn: () => catalogApi.batches(productId) });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["product", productId] });
    qc.invalidateQueries({ queryKey: ["batches", productId] });
    qc.invalidateQueries({ queryKey: ["my-products"] });
    qc.invalidateQueries({ queryKey: ["alerts"] });
  };
  const update = useMutation({
    mutationFn: (body: Parameters<typeof catalogApi.updateProduct>[1]) => catalogApi.updateProduct(productId, body),
    onSuccess: () => { refresh(); notifications.show({ color: "teal", message: "Product saved" }); },
  });
  const receiveForm = useForm({
    initialValues: { batch_number: "", expiry_date: "", quantity: "" as number | string },
    validate: {
      batch_number: (v) => (v.trim() ? null : "Required"),
      expiry_date: (v) => (v && new Date(v) > new Date() ? null : "Enter a future expiry date"),
      quantity: (v) => (Number(v) > 0 ? null : "Enter a quantity"),
    },
  });
  const receive = useMutation({
    mutationFn: (v: typeof receiveForm.values) => catalogApi.receiveBatch(productId, { ...v, quantity: Number(v.quantity) }),
    onSuccess: (b) => { refresh(); receiveForm.reset(); notifications.show({ color: "teal", message: `Received into batch ${b.batch_number}` }); },
  });
  const [adjusting, setAdjusting] = useState<Batch | null>(null);
  const [history, setHistory] = useState<Batch | null>(null);

  if (product.isLoading) return <Loading />;
  if (product.error) return <ErrorNotice error={product.error} />;
  const p = product.data!;

  return (
    <>
      <Anchor component={Link} to="/inventory" size="sm"><Group gap={4}><IconArrowLeft size={14} />Products & stock</Group></Anchor>
      <Group justify="space-between" my="md" wrap="wrap">
        <div>
          <Title order={2}>{p.name} {p.strength}</Title>
          <Text c="dimmed">{p.generic_name} · {money(p.unit_price, p.currency)}</Text>
        </div>
        <Group>
          <StockBadge qty={p.stock_available} reorder={p.reorder_level} />
          {canManage && <Switch label="Listed for pharmacies" checked={p.is_active} onChange={(e) => update.mutate({ is_active: e.currentTarget.checked })} />}
        </Group>
      </Group>
      <Tabs defaultValue="stock">
        <Tabs.List mb="md">
          <Tabs.Tab value="stock">Batches & stock</Tabs.Tab>
          <Tabs.Tab value="details">Product details</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="stock">
          <Grid>
            <Grid.Col span={{ base: 12, lg: 8 }}>
              <Card p={0}>
                <Table.ScrollContainer minWidth={600}>
                  <Table>
                    <Table.Thead><Table.Tr><Table.Th>Batch</Table.Th><Table.Th>Expiry</Table.Th><Table.Th ta="right">Available</Table.Th><Table.Th ta="right">Reserved</Table.Th><Table.Th /></Table.Tr></Table.Thead>
                    <Table.Tbody>
                      {batches.data?.map((b) => (
                        <Table.Tr key={b.id}>
                          <Table.Td fw={500}>{b.batch_number}</Table.Td>
                          <Table.Td><ExpiryBadge expiry={b.expiry_date} /></Table.Td>
                          <Table.Td ta="right">{b.quantity_available}</Table.Td>
                          <Table.Td ta="right">{b.quantity_reserved > 0 ? <Badge variant="light">{b.quantity_reserved}</Badge> : 0}</Table.Td>
                          <Table.Td>
                            <Group gap={4} justify="flex-end" wrap="nowrap">
                              <Button size="compact-xs" variant="subtle" onClick={() => setAdjusting(b)}>Adjust</Button>
                              <Button size="compact-xs" variant="subtle" leftSection={<IconHistory size={12} />} onClick={() => setHistory(b)}>History</Button>
                            </Group>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                      {batches.data?.length === 0 && <Table.Tr><Table.Td colSpan={5}><Text c="dimmed" size="sm" p="sm">No stock yet. Receive your first batch →</Text></Table.Td></Table.Tr>}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              </Card>
              <Text size="xs" c="dimmed" mt="xs">“Reserved” stock is held for orders that haven't been dispatched. Orders always take the earliest-expiring batch first.</Text>
            </Grid.Col>
            <Grid.Col span={{ base: 12, lg: 4 }}>
              <Card>
                <Group gap="xs" mb="sm"><IconPackageImport size={20} /><Title order={5}>Receive stock</Title></Group>
                <form onSubmit={receiveForm.onSubmit((v) => receive.mutate(v))}>
                  <Stack>
                    {receive.error && <ErrorNotice error={receive.error} title="Not received" />}
                    <TextInput label="Batch / lot number" {...receiveForm.getInputProps("batch_number")} />
                    <TextInput type="date" label="Expiry date" {...receiveForm.getInputProps("expiry_date")} />
                    <NumberInput label="Quantity (packs)" min={1} {...receiveForm.getInputProps("quantity")} />
                    <Button type="submit" loading={receive.isPending}>Receive</Button>
                  </Stack>
                </form>
              </Card>
            </Grid.Col>
          </Grid>
        </Tabs.Panel>
        <Tabs.Panel value="details">
          <Card><ProductForm initial={p} onSubmit={(v) => update.mutate(v)} submitting={update.isPending} error={update.error} /></Card>
        </Tabs.Panel>
      </Tabs>
      <AdjustModal batch={adjusting} onClose={() => setAdjusting(null)} onDone={refresh} />
      <HistoryModal batch={history} onClose={() => setHistory(null)} />
    </>
  );
}

function AdjustModal({ batch, onClose, onDone }: { batch: Batch | null; onClose: () => void; onDone: () => void }) {
  const form = useForm({ initialValues: { direction: "remove", amount: "" as number | string, reason: "ADJUSTMENT", note: "" } });
  const adjust = useMutation({
    mutationFn: (v: typeof form.values) =>
      catalogApi.adjustBatch(batch!.id, { change: (v.direction === "remove" ? -1 : 1) * Number(v.amount), reason: v.reason, note: v.note || undefined }),
    onSuccess: () => { onDone(); form.reset(); onClose(); },
  });
  return (
    <Modal opened={!!batch} onClose={onClose} title={`Adjust batch ${batch?.batch_number}`}>
      <form onSubmit={form.onSubmit((v) => adjust.mutate(v))}>
        <Stack>
          {adjust.error && <ErrorNotice error={adjust.error} title="Not adjusted" />}
          <Text size="sm">Currently {batch?.quantity_available} available.</Text>
          <Group grow>
            <Select label="Action" allowDeselect={false} data={[{ value: "remove", label: "Remove stock" }, { value: "add", label: "Add stock" }]} {...form.getInputProps("direction")} />
            <NumberInput label="Quantity" min={1} required {...form.getInputProps("amount")} />
          </Group>
          <Select label="Reason" allowDeselect={false} data={REASONS} {...form.getInputProps("reason")} />
          <TextInput label="Note (kept in audit history)" {...form.getInputProps("note")} />
          <Group justify="flex-end"><Button variant="default" onClick={onClose}>Cancel</Button><Button type="submit" loading={adjust.isPending}>Save adjustment</Button></Group>
        </Stack>
      </form>
    </Modal>
  );
}

function HistoryModal({ batch, onClose }: { batch: Batch | null; onClose: () => void }) {
  const moves = useQuery({ queryKey: ["movements", batch?.id], queryFn: () => catalogApi.movements(batch!.id), enabled: !!batch });
  return (
    <Modal opened={!!batch} onClose={onClose} title={`Stock history · ${batch?.batch_number}`} size="lg">
      {moves.isLoading && <Loading />}
      <Table>
        <Table.Thead><Table.Tr><Table.Th>When</Table.Th><Table.Th>Event</Table.Th><Table.Th ta="right">Change</Table.Th><Table.Th>Reference / note</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {moves.data?.map((m) => (
            <Table.Tr key={m.id}>
              <Table.Td>{dateTime(m.created_at)}</Table.Td>
              <Table.Td>{m.reason.charAt(0) + m.reason.slice(1).toLowerCase()}</Table.Td>
              <Table.Td ta="right" c={m.change > 0 ? "teal" : m.change < 0 ? "red" : undefined}>{m.change > 0 ? `+${m.change}` : m.change}</Table.Td>
              <Table.Td>{[m.reference, m.note].filter(Boolean).join(" · ")}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Modal>
  );
}

import { Anchor, Button, Card, Grid, Group, Modal, Stack, Table, Text, Textarea, Timeline, Title } from "@mantine/core";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { IconArrowLeft, IconMessage, IconPrinter } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { openStartConversation } from "@/modules/messaging/StartConversation";
import { useAccount } from "@/shared/auth/session";
import { Money } from "@/shared/currency";
import { date, dateTime, money } from "@/shared/format";
import { ErrorNotice, ExpiryBadge, Loading, ORDER_STATUS, StatusBadge } from "@/shared/ui";
import { ordersApi, PAYMENT_METHODS, type OrderStatus } from "./api";

const ACTIONS: Record<OrderStatus, { label: string; color?: string; confirm?: string; needsNote?: boolean }> = {
  ACCEPTED: { label: "Accept order" },
  DISPATCHED: { label: "Mark as dispatched", confirm: "Confirm the order has left your premises. Reserved stock will be deducted." },
  DELIVERED: { label: "Confirm delivery", confirm: "Confirm all items were received in good condition." },
  REJECTED: { label: "Reject", color: "red", needsNote: true },
  CANCELLED: { label: "Cancel order", color: "red", confirm: "Cancel this order? Reserved stock will be released." },
  SUBMITTED: { label: "" },
};

export default function OrderDetailPage() {
  const id = Number(useParams().orderId);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { isPharmacy, isAdmin } = useAccount();
  const order = useQuery({ queryKey: ["orders", id], queryFn: () => ordersApi.get(id) });
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");
  const change = useMutation({
    mutationFn: ({ status, note }: { status: OrderStatus; note?: string }) => ordersApi.changeStatus(id, status, note),
    onSuccess: (o) => {
      qc.setQueryData(["orders", id], o);
      ["orders", "summary", "budget"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      notifications.show({ color: "teal", message: `Order ${o.order_number}: ${ORDER_STATUS[o.status].label}` });
      setRejecting(false);
    },
    onError: (e) => notifications.show({ color: "red", title: "Not updated", message: e.message }),
  });

  if (order.isLoading) return <Loading />;
  if (order.error) return <ErrorNotice error={order.error} />;
  const o = order.data!;

  const act = (status: OrderStatus) => {
    const a = ACTIONS[status];
    if (a.needsNote) return setRejecting(true);
    if (!a.confirm) return change.mutate({ status });
    modals.openConfirmModal({
      title: a.label, children: <Text size="sm">{a.confirm}</Text>,
      labels: { confirm: a.label, cancel: "Back" }, confirmProps: { color: a.color },
      onConfirm: () => change.mutate({ status }),
    });
  };

  return (
    <div className="printable">
      <Anchor component={Link} to="/orders" size="sm" className="no-print"><Group gap={4}><IconArrowLeft size={14} />Orders</Group></Anchor>
      <Group justify="space-between" my="md" align="flex-start" wrap="wrap">
        <div>
          <Group gap="sm"><Title order={2}>{o.order_number}</Title><StatusBadge status={o.status} size="lg" /></Group>
          <Text c="dimmed" size="sm">{ORDER_STATUS[o.status].help}</Text>
        </div>
        <Group className="no-print">
          {!isAdmin && (
            <Button variant="default" leftSection={<IconMessage size={16} />}
              onClick={() => openStartConversation({
                orgId: isPharmacy ? o.supplier_org_id : o.pharmacy_org_id, orgName: isPharmacy ? o.supplier_name : o.pharmacy_name,
                subject: `Order ${o.order_number}`, orderNumber: o.order_number, onCreated: (cid) => navigate(`/messages/${cid}`),
              })}>Message {isPharmacy ? "supplier" : "pharmacy"}</Button>
          )}
          <Button variant="default" leftSection={<IconPrinter size={16} />} onClick={() => window.print()}>Print</Button>
          {o.allowed_transitions.map((s) => (
            <Button key={s} color={ACTIONS[s].color} variant={ACTIONS[s].color ? "light" : "filled"} loading={change.isPending && change.variables?.status === s} onClick={() => act(s)}>
              {ACTIONS[s].label}
            </Button>
          ))}
        </Group>
      </Group>

      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, lg: 8 }}>
          <Card p={0} mb="lg">
            <Table.ScrollContainer minWidth={640}>
              <Table>
                <Table.Thead><Table.Tr><Table.Th>Item</Table.Th><Table.Th>Batch · expiry</Table.Th><Table.Th ta="right">Qty</Table.Th><Table.Th ta="right">Unit</Table.Th><Table.Th ta="right">Total</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {o.lines.map((l) => (
                    <Table.Tr key={l.id}>
                      <Table.Td><Text fw={500} size="sm">{l.product_name} {l.strength}</Text><Text size="xs" c="dimmed">{l.generic_name}{l.pack_size && ` · ${l.pack_size}`}{l.schedule && ` · ${l.schedule}`}{l.mcaz_registration_number && ` · MCAZ ${l.mcaz_registration_number}`}</Text></Table.Td>
                      <Table.Td><Stack gap={2}>{l.allocations.map((a) => <Group key={a.batch_number} gap={6}><Text size="xs">{a.batch_number} ×{a.quantity}</Text><ExpiryBadge expiry={a.expiry_date} /></Group>)}</Stack></Table.Td>
                      <Table.Td ta="right">{l.quantity}</Table.Td>
                      <Table.Td ta="right">{money(l.unit_price, o.currency)}</Table.Td>
                      <Table.Td ta="right" fw={600}>{money(l.line_total, o.currency)}</Table.Td>
                    </Table.Tr>
                  ))}
                  <Table.Tr><Table.Td colSpan={4} ta="right" fw={600}>Total</Table.Td><Table.Td ta="right"><Money amount={o.subtotal} currency={o.currency} rates={o.fx_rates} size="lg" fw={700} /></Table.Td></Table.Tr>
                  {o.fx_rates?.ZWG && <Table.Tr><Table.Td colSpan={5} ta="right"><Text size="xs" c="dimmed">Rate at checkout: 1 USD = {Number(o.fx_rates.ZWG).toLocaleString("en-ZW", { maximumFractionDigits: 4 })} ZiG</Text></Table.Td></Table.Tr>}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Card>
          <Grid>
            <Grid.Col span={{ base: 12, sm: 6 }}>
              <Card h="100%">
                <Text fw={600} mb="xs">From (pharmacy)</Text>
                <Text size="sm">{o.pharmacy_name}</Text>
                <Text size="sm">{o.delivery_address}</Text>
                <Text size="sm">{o.contact_name} · {o.contact_phone}</Text>
                <Text size="xs" c="dimmed" mt="xs">Placed by {o.created_by_name} on {date(o.created_at)}</Text>
              </Card>
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6 }}>
              <Card h="100%">
                <Text fw={600} mb="xs">To (supplier)</Text>
                <Text size="sm">{o.supplier_name}</Text>
                <Text size="sm" mt="xs">Payment: {PAYMENT_METHODS[o.payment_method]}</Text>
                {o.notes && <Text size="sm" mt="xs" style={{ whiteSpace: "pre-wrap" }}>Notes: {o.notes}</Text>}
              </Card>
            </Grid.Col>
          </Grid>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 4 }}>
          <Card>
            <Text fw={600} mb="md">Progress</Text>
            <Timeline active={o.history.length - 1} bulletSize={18} lineWidth={2}>
              {o.history.map((h, i) => (
                <Timeline.Item key={i} title={ORDER_STATUS[h.status].label} color={ORDER_STATUS[h.status].color}>
                  <Text size="xs" c="dimmed">{dateTime(h.at)} · {h.actor_name}, {h.actor_org_name}</Text>
                  {h.note && <Text size="sm" mt={4}>“{h.note}”</Text>}
                </Timeline.Item>
              ))}
            </Timeline>
          </Card>
        </Grid.Col>
      </Grid>

      <Modal opened={rejecting} onClose={() => setRejecting(false)} title="Reject order">
        <Stack>
          <Textarea label="Reason (shown to the pharmacy)" required autosize minRows={3} autoFocus value={note} onChange={(e) => setNote(e.currentTarget.value)} placeholder="e.g. Item out of stock until next week" />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setRejecting(false)}>Back</Button>
            <Button color="red" disabled={!note.trim()} loading={change.isPending} onClick={() => change.mutate({ status: "REJECTED", note })}>Reject order</Button>
          </Group>
        </Stack>
      </Modal>
    </div>
  );
}

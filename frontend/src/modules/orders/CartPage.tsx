import { ActionIcon, Alert, Button, Card, Divider, Grid, Group, NumberInput, Select, Stack, Table, Text, Textarea, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconAlertTriangle, IconCircleCheck, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useAccount } from "@/shared/auth/session";
import { money } from "@/shared/format";
import { EmptyState, ErrorNotice, PageHeader } from "@/shared/ui";
import { ordersApi, PAYMENT_METHODS, type Order, type PaymentMethod } from "./api";
import { useCart, type CartLine } from "./cart";

export default function CartPage() {
  const { lines, checkoutKey, setQuantity, remove, clear } = useCart();
  const { organization, user } = useAccount();
  const qc = useQueryClient();
  const budget = useQuery({ queryKey: ["budget"], queryFn: ordersApi.budget });
  const [placed, setPlaced] = useState<Order[] | null>(null);

  const groups = useMemo(() => {
    const m = new Map<number, { supplier: string; currency: string; lines: CartLine[]; total: number }>();
    for (const l of Object.values(lines)) {
      const g = m.get(l.product.supplier_org_id) ?? { supplier: l.product.supplier_name, currency: l.product.currency, lines: [], total: 0 };
      g.lines.push(l);
      g.total += Number(l.product.unit_price) * l.quantity;
      m.set(l.product.supplier_org_id, g);
    }
    return [...m.values()];
  }, [lines]);
  const total = groups.reduce((s, g) => s + g.total, 0);
  const currency = groups[0]?.currency ?? "USD";
  const b = budget.data;
  const overBudget = b?.is_set && b.currency === currency && total > Number(b.remaining);

  const form = useForm({
    initialValues: {
      delivery_address: [organization?.address, organization?.city].filter(Boolean).join(", "),
      contact_name: user?.full_name ?? "",
      contact_phone: organization?.phone ?? user?.phone ?? "",
      payment_method: "CASH_ON_DELIVERY" as PaymentMethod,
      notes: "",
    },
    validate: {
      delivery_address: (v) => (v.trim().length >= 3 ? null : "Where should the order be delivered?"),
      contact_name: (v) => (v.trim().length >= 2 ? null : "Required"),
      contact_phone: (v) => (v.trim().length >= 5 ? null : "A phone number for the driver"),
    },
  });
  const checkout = useMutation({
    mutationFn: (v: typeof form.values) =>
      ordersApi.checkout({ ...v, notes: v.notes || undefined, idempotency_key: checkoutKey, lines: Object.values(lines).map((l) => ({ product_id: l.product.id, quantity: l.quantity })) }),
    onSuccess: (orders) => {
      setPlaced(orders);
      clear();
      ["orders", "summary", "budget", "catalog"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    },
  });

  if (placed) {
    return (
      <Card maw={640} mx="auto" mt="xl" ta="center">
        <Stack align="center">
          <IconCircleCheck size={56} color="var(--mantine-color-teal-6)" />
          <Title order={3}>Order{placed.length > 1 ? "s" : ""} sent</Title>
          <Text c="dimmed">{placed.length > 1 ? `Your cart was split into ${placed.length} purchase orders, one per supplier.` : "The supplier has been notified."} You'll get a notification when each one is accepted.</Text>
          <Stack gap={4} w="100%">
            {placed.map((o) => (
              <Group key={o.id} justify="space-between" p="sm" style={{ border: "1px solid var(--mantine-color-gray-3)", borderRadius: 8 }}>
                <Text fw={600}>{o.order_number}</Text><Text>{o.supplier_name}</Text><Text fw={600}>{money(o.subtotal, o.currency)}</Text>
                <Button size="xs" variant="light" component={Link} to={`/orders/${o.id}`}>View</Button>
              </Group>
            ))}
          </Stack>
          <Group><Button component={Link} to="/catalog" variant="default">Continue ordering</Button><Button component={Link} to="/orders">Go to my orders</Button></Group>
        </Stack>
      </Card>
    );
  }

  if (!groups.length) {
    return (<><PageHeader title="Cart" /><Card><EmptyState title="Your cart is empty" description="Search for medicines and add quantities to start an order." action={<Button component={Link} to="/catalog">Order medicines</Button>} /></Card></>);
  }

  return (
    <>
      <PageHeader title="Review & place order" description={groups.length > 1 ? `Items from ${groups.length} suppliers — each supplier receives their own purchase order.` : undefined} />
      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, lg: 8 }}>
          <Stack>
            {groups.map((g) => (
              <Card key={g.supplier} p={0}>
                <Group justify="space-between" p="md" bg="var(--mantine-color-gray-0)"><Text fw={600}>{g.supplier}</Text><Text fw={600}>{money(g.total, g.currency)}</Text></Group>
                <Table.ScrollContainer minWidth={560}>
                  <Table>
                    <Table.Tbody>
                      {g.lines.map((l) => (
                        <Table.Tr key={l.product.id}>
                          <Table.Td><Text fw={500} size="sm">{l.product.name} {l.product.strength}</Text><Text size="xs" c="dimmed">{l.product.generic_name} · {l.product.pack_size}</Text></Table.Td>
                          <Table.Td w={120}><Text size="sm">{money(l.product.unit_price, l.product.currency)}</Text></Table.Td>
                          <Table.Td w={110}><NumberInput size="xs" min={1} max={l.product.stock_available} value={l.quantity} onChange={(v) => Number(v) > 0 && setQuantity(l.product.id, Number(v))} aria-label="Quantity" /></Table.Td>
                          <Table.Td w={110} ta="right"><Text fw={600} size="sm">{money(Number(l.product.unit_price) * l.quantity, l.product.currency)}</Text></Table.Td>
                          <Table.Td w={40}><ActionIcon variant="subtle" color="red" onClick={() => remove(l.product.id)} aria-label={`Remove ${l.product.name}`}><IconTrash size={16} /></ActionIcon></Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              </Card>
            ))}
            <Group><Button component={Link} to="/catalog" variant="default">Add more items</Button><Button variant="subtle" color="red" onClick={clear}>Empty cart</Button></Group>
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 4 }}>
          <Card style={{ position: "sticky", top: 76 }}>
            <form onSubmit={form.onSubmit((v) => checkout.mutate(v))}>
              <Stack>
                <Title order={4}>Delivery & payment</Title>
                <TextInput label="Deliver to" required {...form.getInputProps("delivery_address")} />
                <Group grow>
                  <TextInput label="Contact person" required {...form.getInputProps("contact_name")} />
                  <TextInput label="Phone" required {...form.getInputProps("contact_phone")} />
                </Group>
                <Select label="Payment" allowDeselect={false} data={Object.entries(PAYMENT_METHODS).map(([value, label]) => ({ value, label }))} {...form.getInputProps("payment_method")} />
                <Textarea label="Notes for supplier" placeholder="e.g. deliver before 10am, cold-chain items" autosize minRows={2} {...form.getInputProps("notes")} />
                <Divider />
                <Group justify="space-between"><Text>Total</Text><Text size="xl" fw={700}>{money(total, currency)}</Text></Group>
                {overBudget && (
                  <Alert color="orange" icon={<IconAlertTriangle size={18} />} p="sm">
                    This order is over your remaining monthly budget of {money(b!.remaining, b!.currency)}. You can still place it.
                  </Alert>
                )}
                {checkout.error && <ErrorNotice error={checkout.error} title="Order not placed" />}
                <Button type="submit" size="md" loading={checkout.isPending}>Place order{groups.length > 1 ? `s (${groups.length})` : ""}</Button>
                <Text size="xs" c="dimmed" ta="center">Stock is reserved for you as soon as the order is placed.</Text>
              </Stack>
            </form>
          </Card>
        </Grid.Col>
      </Grid>
    </>
  );
}

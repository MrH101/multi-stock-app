import { Badge, Button, Card, Grid, Group, SimpleGrid, Stack, Table, Tabs, Text, Title } from "@mantine/core";
import { IconAlertTriangle, IconBell, IconCash, IconPackage, IconTruckDelivery } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { catalogApi } from "@/modules/catalog/api";
import { ordersApi } from "@/modules/orders/api";
import { InsightsWidget } from "@/modules/insights/InsightsWidget";
import { useAccount } from "@/shared/auth/session";
import { money } from "@/shared/format";
import { ExpiryBadge } from "@/shared/ui";
import { MonthlyChart, RecentOrders, StatCard } from "./widgets";

export default function SupplierDashboard() {
  const { organization } = useAccount();
  const navigate = useNavigate();
  const summary = useQuery({ queryKey: ["summary"], queryFn: ordersApi.summary });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => catalogApi.alerts(180) });
  const s = summary.data;
  const a = alerts.data;
  const alertCount = (a?.expiring.length ?? 0) + (a?.expired.length ?? 0) + (a?.low_stock.length ?? 0);

  return (
    <>
      <Group justify="space-between" mb="lg">
        <div><Title order={2}>{organization?.name}</Title><Text c="dimmed">Supplier dashboard</Text></div>
        <Button component={Link} to="/inventory" variant="light" leftSection={<IconPackage size={18} />}>Products & stock</Button>
      </Group>
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} mb="lg">
        <StatCard label="New orders to review" value={s?.counts.SUBMITTED ?? "—"} icon={IconBell} color={s?.counts.SUBMITTED ? "red" : "blue"} to="/orders" />
        <StatCard label="Accepted, to dispatch" value={s?.counts.ACCEPTED ?? "—"} icon={IconTruckDelivery} color="violet" to="/orders" />
        <StatCard label="Sales this month" value={s ? money(s.month_total, s.currency) : "—"} icon={IconCash} />
        <StatCard label="Stock alerts" value={alertCount} icon={IconAlertTriangle} color={alertCount ? "orange" : "gray"} hint="Expiring within 6 months or low" />
      </SimpleGrid>
      <InsightsWidget />
      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, lg: 7 }}><RecentOrders title="Orders needing action" status={["SUBMITTED", "ACCEPTED"]} counterpart="pharmacy" /></Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card p={0} h="100%">
            <Tabs defaultValue="expiring">
              <Tabs.List px="md" pt="sm">
                <Tabs.Tab value="expiring">Expiring <Badge size="xs" ml={4} variant="light">{(a?.expiring.length ?? 0) + (a?.expired.length ?? 0)}</Badge></Tabs.Tab>
                <Tabs.Tab value="low">Low stock <Badge size="xs" ml={4} variant="light">{a?.low_stock.length ?? 0}</Badge></Tabs.Tab>
              </Tabs.List>
              <Tabs.Panel value="expiring">
                <Table>
                  <Table.Tbody>
                    {[...(a?.expired ?? []), ...(a?.expiring ?? [])].slice(0, 8).map((b) => (
                      <Table.Tr key={b.batch_id} style={{ cursor: "pointer" }} onClick={() => navigate(`/inventory/${b.product_id}`)}>
                        <Table.Td><Text size="sm" fw={500}>{b.product_name}</Text><Text size="xs" c="dimmed">Batch {b.batch_number} · {b.quantity_available} units</Text></Table.Td>
                        <Table.Td ta="right"><ExpiryBadge expiry={b.expiry_date} /></Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
                {alertCount === 0 && <Text size="sm" c="dimmed" p="md">No batches expiring in the next 6 months.</Text>}
              </Tabs.Panel>
              <Tabs.Panel value="low">
                <Stack gap={0}>
                  {a?.low_stock.map((p) => (
                    <Group key={p.product_id} justify="space-between" p="sm" style={{ borderBottom: "1px solid var(--mantine-color-gray-2)", cursor: "pointer" }} onClick={() => navigate(`/inventory/${p.product_id}`)}>
                      <Text size="sm" fw={500}>{p.product_name}</Text>
                      <Text size="sm" c="orange">{p.stock_available} left (reorder at {p.reorder_level})</Text>
                    </Group>
                  ))}
                  {a?.low_stock.length === 0 && <Text size="sm" c="dimmed" p="md">Nothing below its reorder level.</Text>}
                </Stack>
              </Tabs.Panel>
            </Tabs>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 8 }}><MonthlyChart summary={s} label="Sales" /></Grid.Col>
        <Grid.Col span={{ base: 12, lg: 4 }}>
          <Card h="100%">
            <Text fw={600} mb="sm">Top products</Text>
            {s?.top_products.length ? s.top_products.map((p) => (
              <Group key={p.product_id} justify="space-between" mb={6}><Text size="sm">{p.product_name}</Text><Text size="sm" fw={600}>{money(p.total, s.currency)}</Text></Group>
            )) : <Text size="sm" c="dimmed">No sales yet.</Text>}
          </Card>
        </Grid.Col>
      </Grid>
    </>
  );
}

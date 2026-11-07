import { BarChart } from "@mantine/charts";
import { Button, Card, Group, Stack, Table, Text, ThemeIcon } from "@mantine/core";
import type { Icon } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { messagingApi } from "@/modules/messaging/api";
import { ordersApi, type DashboardSummary, type OrderStatus } from "@/modules/orders/api";
import { dateTime, fromNow, money } from "@/shared/format";
import { EmptyState, StatusBadge } from "@/shared/ui";

export function StatCard({ label, value, icon: I, color = "teal", hint, to }: { label: string; value: ReactNode; icon: Icon; color?: string; hint?: string; to?: string }) {
  const body = (
    <Card h="100%" style={to ? { cursor: "pointer" } : undefined}>
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <div>
          <Text size="sm" c="dimmed">{label}</Text>
          <Text size="28px" fw={700} mt={4} lh={1.2}>{value}</Text>
          {hint && <Text size="xs" c="dimmed" mt={4}>{hint}</Text>}
        </div>
        <ThemeIcon size={42} radius="md" variant="light" color={color}><I size={22} /></ThemeIcon>
      </Group>
    </Card>
  );
  return to ? <Link to={to} style={{ textDecoration: "none", color: "inherit" }}>{body}</Link> : body;
}

export function MonthlyChart({ summary, label }: { summary?: DashboardSummary; label: string }) {
  const data = (summary?.monthly ?? []).map((m) => ({ month: new Date(`${m.month}-01`).toLocaleString("en", { month: "short" }), total: Number(m.total) }));
  return (
    <Card h="100%">
      <Text fw={600} mb="md">{label} · last 6 months</Text>
      <BarChart h={220} data={data} dataKey="month" series={[{ name: "total", label, color: "teal.6" }]}
        valueFormatter={(v) => money(v, summary?.currency ?? "USD")} withLegend={false} gridAxis="y" />
    </Card>
  );
}

export function RecentOrders({ status, title, counterpart }: { status?: OrderStatus[]; title: string; counterpart: "supplier" | "pharmacy" }) {
  const navigate = useNavigate();
  const orders = useQuery({ queryKey: ["orders", "recent", status], queryFn: () => ordersApi.list({ status, page: 1 }) });
  const items = orders.data?.items.slice(0, 6) ?? [];
  return (
    <Card p={0} h="100%">
      <Group justify="space-between" p="md"><Text fw={600}>{title}</Text><Button component={Link} to="/orders" size="compact-sm" variant="subtle">View all</Button></Group>
      {items.length === 0 && !orders.isLoading ? <EmptyState title="Nothing here yet" /> : (
        <Table>
          <Table.Tbody>
            {items.map((o) => (
              <Table.Tr key={o.id} style={{ cursor: "pointer" }} onClick={() => navigate(`/orders/${o.id}`)}>
                <Table.Td><Text fw={600} size="sm">{o.order_number}</Text><Text size="xs" c="dimmed">{counterpart === "supplier" ? o.supplier_name : o.pharmacy_name}</Text></Table.Td>
                <Table.Td><Text size="xs" c="dimmed">{dateTime(o.created_at)}</Text></Table.Td>
                <Table.Td ta="right"><Text size="sm" fw={600}>{money(o.subtotal, o.currency)}</Text></Table.Td>
                <Table.Td><StatusBadge status={o.status} size="sm" /></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Card>
  );
}

export function LatestAnnouncements() {
  const list = useQuery({ queryKey: ["broadcasts"], queryFn: messagingApi.broadcasts });
  const items = list.data?.slice(0, 3) ?? [];
  return (
    <Card h="100%">
      <Group justify="space-between" mb="sm"><Text fw={600}>Announcements</Text><Button component={Link} to="/announcements" size="compact-sm" variant="subtle">All</Button></Group>
      {items.length === 0 ? <Text size="sm" c="dimmed">No announcements yet.</Text> : (
        <Stack gap="sm">
          {items.map((b) => (
            <div key={b.id}>
              <Text size="sm" fw={600}>{b.title}</Text>
              <Text size="xs" c="dimmed" lineClamp={2}>{b.body}</Text>
              <Text size="xs" c="dimmed">{b.sender_org_name} · {fromNow(b.created_at)}</Text>
            </div>
          ))}
        </Stack>
      )}
    </Card>
  );
}

import { Button, Grid, Group, SimpleGrid, Text, Title } from "@mantine/core";
import { IconClipboardList, IconCash, IconSearch, IconTruckDelivery } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ordersApi } from "@/modules/orders/api";
import { BudgetCard } from "@/modules/orders/BudgetCard";
import { InsightsWidget } from "@/modules/insights/InsightsWidget";
import { useAccount } from "@/shared/auth/session";
import { money } from "@/shared/format";
import { LatestAnnouncements, MonthlyChart, RecentOrders, StatCard } from "./widgets";

export default function PharmacyDashboard() {
  const { user, organization } = useAccount();
  const summary = useQuery({ queryKey: ["summary"], queryFn: ordersApi.summary });
  const s = summary.data;
  const hour = new Date().getHours();

  return (
    <>
      <Group justify="space-between" mb="lg" wrap="wrap">
        <div>
          <Title order={2}>Good {hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening"}, {user?.full_name.split(" ")[0]}</Title>
          <Text c="dimmed">{organization?.name}</Text>
        </div>
        <Button component={Link} to="/catalog" size="lg" leftSection={<IconSearch size={20} />}>Order medicines</Button>
      </Group>
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} mb="lg">
        <StatCard label="Awaiting supplier" value={s?.counts.SUBMITTED ?? "—"} icon={IconClipboardList} color="blue" to="/orders" />
        <StatCard label="On the way" value={(s?.counts.ACCEPTED ?? 0) + (s?.counts.DISPATCHED ?? 0)} icon={IconTruckDelivery} color="violet" hint="Accepted or dispatched" to="/orders" />
        <StatCard label="Spent this month" value={s ? money(s.month_total, s.currency) : "—"} icon={IconCash} />
        <BudgetCard />
      </SimpleGrid>
      <InsightsWidget />
      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, lg: 7 }}><RecentOrders title="Recent orders" counterpart="supplier" /></Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}><LatestAnnouncements /></Grid.Col>
        <Grid.Col span={12}><MonthlyChart summary={s} label="Purchases" /></Grid.Col>
      </Grid>
    </>
  );
}

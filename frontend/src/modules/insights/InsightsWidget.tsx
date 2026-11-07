import { Button, Card, Grid, Group, Stack, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertRow } from "./AlertList";
import { insightsApi } from "./api";
import { BriefingCard } from "./BriefingCard";

/** Dashboard strip: the briefing plus the most urgent open alerts. */
export function InsightsWidget() {
  const alerts = useQuery({ queryKey: ["insights", "alerts", "live"], queryFn: () => insightsApi.alerts("live"), refetchInterval: 60_000 });
  const top = (alerts.data ?? []).filter((a) => a.status === "OPEN" && a.severity !== "info").slice(0, 4);
  return (
    <Grid gutter="lg" mb="lg">
      <Grid.Col span={{ base: 12, lg: 6 }}><BriefingCard withLink maxActions={3} /></Grid.Col>
      <Grid.Col span={{ base: 12, lg: 6 }}>
        <Card h="100%">
          <Group justify="space-between" mb="sm">
            <Text fw={600}>Needs attention</Text>
            <Button component={Link} to="/insights" size="compact-sm" variant="subtle">See all</Button>
          </Group>
          {top.length === 0 ? (
            <Text size="sm" c="dimmed">{alerts.isLoading ? "Checking…" : "No urgent alerts. Nice work."}</Text>
          ) : (
            <Stack gap="xs">
              {top.map((a) => (
                <Link key={a.id} to={a.link ?? "/insights"} style={{ textDecoration: "none", color: "inherit" }}>
                  <AlertRow alert={a} compact />
                </Link>
              ))}
            </Stack>
          )}
        </Card>
      </Grid.Col>
    </Grid>
  );
}

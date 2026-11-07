import { Grid, Group, SegmentedControl, Stack, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fromNow } from "@/shared/format";
import { ErrorNotice, Loading, PageHeader } from "@/shared/ui";
import { AlertList } from "./AlertList";
import { insightsApi, SEVERITY, type Severity } from "./api";
import { AssistantPanel } from "./AssistantPanel";
import { BriefingCard } from "./BriefingCard";

type Filter = "all" | Severity | "resolved";

export default function InsightsPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const state = filter === "resolved" ? "resolved" : "live";
  const alerts = useQuery({ queryKey: ["insights", "alerts", state], queryFn: () => insightsApi.alerts(state), refetchInterval: 60_000 });
  const status = useQuery({ queryKey: ["insights", "status"], queryFn: insightsApi.status, staleTime: 60_000 });
  const live = useQuery({ queryKey: ["insights", "alerts", "live"], queryFn: () => insightsApi.alerts("live"), enabled: state !== "live" });
  const liveItems = (state === "live" ? alerts.data : live.data) ?? [];
  const count = (s: Severity) => liveItems.filter((a) => a.severity === s).length;
  const items = (alerts.data ?? []).filter((a) => filter === "all" || filter === "resolved" || a.severity === filter);
  const run = status.data?.last_run;

  return (
    <>
      <PageHeader
        title="Insights"
        description="Your monitoring assistant watches stock, expiry dates, orders and budgets, and tells you what needs attention."
      />
      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Stack gap="lg">
            <BriefingCard />
            <div>
              <Group justify="space-between" mb="sm" wrap="wrap">
                <SegmentedControl
                  value={filter}
                  onChange={(v) => setFilter(v as Filter)}
                  data={[
                    { value: "all", label: `All (${liveItems.length})` },
                    { value: "critical", label: `${SEVERITY.critical.label} (${count("critical")})` },
                    { value: "warning", label: `${SEVERITY.warning.label} (${count("warning")})` },
                    { value: "info", label: `${SEVERITY.info.label} (${count("info")})` },
                    { value: "resolved", label: "Cleared" },
                  ]}
                />
                {run && <Text size="xs" c="dimmed">Last checked {fromNow(run.finished_at ?? run.started_at)} · every {Math.round(status.data!.interval_minutes)} min</Text>}
              </Group>
              {alerts.isLoading ? <Loading /> : alerts.error ? <ErrorNotice error={alerts.error} /> : (
                <AlertList alerts={items} emptyText={filter === "resolved" ? "Nothing has cleared yet." : "The monitor hasn't found anything that needs attention."} />
              )}
            </div>
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <div style={{ position: "sticky", top: 76 }}>
            <AssistantPanel />
          </div>
        </Grid.Col>
      </Grid>
    </>
  );
}

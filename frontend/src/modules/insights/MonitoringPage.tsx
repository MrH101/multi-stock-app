import { Badge, Button, Card, Grid, Group, SimpleGrid, Table, Text, ThemeIcon } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconActivity, IconAlertTriangle, IconPlayerPlay, IconRobot, IconServer } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { StatCard } from "@/modules/dashboard/widgets";
import { dateTime, fromNow } from "@/shared/format";
import { ErrorNotice, Loading, PageHeader } from "@/shared/ui";
import { AlertList } from "./AlertList";
import { DOMAIN_LABEL, insightsApi } from "./api";

const RUN_COLOR = { OK: "green", PARTIAL: "orange", FAILED: "red", RUNNING: "blue" } as const;

export default function MonitoringPage() {
  const qc = useQueryClient();
  const overview = useQuery({ queryKey: ["insights", "overview"], queryFn: insightsApi.overview, refetchInterval: 30_000 });
  const ops = useQuery({ queryKey: ["insights", "alerts", "live"], queryFn: () => insightsApi.alerts("live") });
  const run = useMutation({
    mutationFn: insightsApi.runNow,
    onSuccess: (r) => {
      notifications.show({ title: `Monitor run ${r.status.toLowerCase()}`, message: `${r.findings} findings, ${r.opened} new, ${r.resolved} cleared, ${r.notified} notifications sent.` });
      qc.invalidateQueries({ queryKey: ["insights"] });
    },
  });
  if (overview.isLoading) return <Loading />;
  if (overview.error) return <ErrorNotice error={overview.error} />;
  const o = overview.data!;
  const down = Object.values(o.services).filter((s) => !s.up).length;

  return (
    <>
      <PageHeader
        title="Monitoring"
        description="Platform health, the monitoring agent's runs and alerts across all organisations."
        actions={<Button leftSection={<IconPlayerPlay size={16} />} loading={run.isPending} onClick={() => run.mutate()}>Run checks now</Button>}
      />
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} mb="lg">
        <StatCard label="Services up" value={`${Object.keys(o.services).length - down}/${Object.keys(o.services).length}`} icon={IconServer} color={down ? "red" : "green"} />
        <StatCard label="Urgent alerts (all orgs)" value={o.alerts_by_severity.critical} icon={IconAlertTriangle} color={o.alerts_by_severity.critical ? "red" : "gray"} hint={`${o.alerts_by_severity.warning} to review · ${o.alerts_by_severity.info} FYI`} />
        <StatCard label="Last run" value={o.runs[0] ? fromNow(o.runs[0].started_at) : "never"} icon={IconActivity} color={o.runs[0] ? RUN_COLOR[o.runs[0].status] : "gray"} hint={o.runs[0] ? `${o.runs[0].status} · ${o.runs[0].duration_seconds ?? "–"}s` : undefined} />
        <StatCard label="AI (Caimex)" value={o.llm.enabled ? `$${o.llm.cost_usd.toFixed(4)}` : "Off"} icon={IconRobot} color={o.llm.last_error ? "orange" : o.llm.enabled ? "grape" : "gray"} hint={o.llm.enabled ? `${o.llm.requests} calls · ${o.llm.failures} failed since restart` : "Set CAIMEX_API_KEY to enable"} />
      </SimpleGrid>
      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card h="100%">
            <Text fw={600} mb="sm">Service health</Text>
            <Table>
              <Table.Tbody>
                {Object.entries(o.services).map(([name, s]) => (
                  <Table.Tr key={name}>
                    <Table.Td><Group gap="xs"><ThemeIcon size={10} radius="xl" color={s.up ? "green" : "red"} /><Text size="sm" tt="capitalize">{name}</Text></Group></Table.Td>
                    <Table.Td><Text size="sm" c="dimmed">{s.up ? `${s.latency_ms} ms` : s.detail}</Text></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            <Text fw={600} mt="lg" mb="xs">Live alerts by area</Text>
            <Group gap="xs">
              {Object.entries(o.alerts_by_domain).map(([d, n]) => <Badge key={d} variant="light">{DOMAIN_LABEL[d] ?? d}: {n}</Badge>)}
              {Object.keys(o.alerts_by_domain).length === 0 && <Text size="sm" c="dimmed">None</Text>}
            </Group>
            {o.llm.enabled && (
              <>
                <Text fw={600} mt="lg" mb={4}>AI model</Text>
                <Text size="sm">{o.llm.last_model ?? o.llm.model} <Text span c="dimmed" size="xs">(fallbacks: {o.llm.fallback_models.join(", ") || "none"})</Text></Text>
                {o.llm.last_error && <Text size="xs" c="orange">Last error: {o.llm.last_error}</Text>}
              </>
            )}
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card p={0} h="100%">
            <Text fw={600} p="md">Recent runs</Text>
            <Table.ScrollContainer minWidth={520}>
              <Table>
                <Table.Thead>
                  <Table.Tr><Table.Th>Started</Table.Th><Table.Th>Result</Table.Th><Table.Th>Findings</Table.Th><Table.Th>New / cleared</Table.Th><Table.Th>Notified</Table.Th></Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {o.runs.map((r) => (
                    <Table.Tr key={r.id} title={r.errors.join("\n")}>
                      <Table.Td><Text size="sm">{dateTime(r.started_at)}</Text><Text size="xs" c="dimmed">{r.trigger}</Text></Table.Td>
                      <Table.Td><Badge color={RUN_COLOR[r.status]} variant="light">{r.status}</Badge></Table.Td>
                      <Table.Td>{r.findings}</Table.Td>
                      <Table.Td>{r.opened} / {r.resolved}</Table.Td>
                      <Table.Td>{r.notified}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
            {o.runs.some((r) => r.errors.length) && (
              <Text size="xs" c="dimmed" p="md">Hover a run to see its errors. Partial runs leave alerts from unreachable services untouched.</Text>
            )}
          </Card>
        </Grid.Col>
        <Grid.Col span={12}>
          <Text fw={600} mb="sm">Platform alerts</Text>
          <AlertList alerts={ops.data ?? []} emptyText="All services are healthy and every data source was readable on the last run." />
        </Grid.Col>
      </Grid>
    </>
  );
}

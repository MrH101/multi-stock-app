import { Badge, Button, Card, Group, Stack, Text, ThemeIcon } from "@mantine/core";
import {
  IconCalendarDue, IconCash, IconCheck, IconInfoCircle, IconPackage, IconServer, IconTruckDelivery,
} from "@tabler/icons-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fromNow } from "@/shared/format";
import { EmptyState } from "@/shared/ui";
import { DOMAIN_LABEL, insightsApi, SEVERITY, type Alert } from "./api";

const DOMAIN_ICON: Record<string, typeof IconPackage> = {
  stock: IconPackage,
  expiry: IconCalendarDue,
  order: IconTruckDelivery,
  budget: IconCash,
  supply: IconPackage,
  platform: IconServer,
};

export function SeverityBadge({ severity }: { severity: Alert["severity"] }) {
  const s = SEVERITY[severity];
  return <Badge color={s.color} variant={severity === "critical" ? "filled" : "light"} size="sm">{s.label}</Badge>;
}

export function AlertRow({ alert, compact = false }: { alert: Alert; compact?: boolean }) {
  const qc = useQueryClient();
  const ack = useMutation({
    mutationFn: () => insightsApi.acknowledge(alert.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["insights"] }),
  });
  const Icon = DOMAIN_ICON[alert.domain] ?? IconInfoCircle;
  const resolved = alert.status === "RESOLVED";
  return (
    <Card p="md" style={{ borderLeft: `4px solid var(--mantine-color-${SEVERITY[alert.severity].color}-6)`, opacity: resolved ? 0.7 : 1 }}>
      <Group align="flex-start" wrap="nowrap" gap="md">
        <ThemeIcon variant="light" color={SEVERITY[alert.severity].color} size={36} radius="md">
          <Icon size={20} />
        </ThemeIcon>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Group gap={6} mb={2} wrap="wrap">
            <SeverityBadge severity={alert.severity} />
            <Text size="xs" c="dimmed">{DOMAIN_LABEL[alert.domain] ?? alert.domain} · since {fromNow(alert.first_seen)}</Text>
            {alert.status === "ACKNOWLEDGED" && <Badge size="xs" variant="outline" color="gray">Seen by {alert.acknowledged_by}</Badge>}
            {resolved && <Badge size="xs" variant="light" color="green">Cleared {alert.resolved_at ? fromNow(alert.resolved_at) : ""}</Badge>}
          </Group>
          <Text fw={600}>{alert.title}</Text>
          {!compact && <Text size="sm" c="dimmed" mt={2}>{alert.body}</Text>}
        </div>
        {!compact && (
          <Stack gap={6} align="flex-end" style={{ flexShrink: 0 }}>
            {alert.link && <Button component={Link} to={alert.link} size="compact-sm" variant="light">Open</Button>}
            {alert.status === "OPEN" && (
              <Button size="compact-sm" variant="subtle" color="gray" leftSection={<IconCheck size={14} />} loading={ack.isPending} onClick={() => ack.mutate()}>
                Got it
              </Button>
            )}
          </Stack>
        )}
      </Group>
    </Card>
  );
}

export function AlertList({ alerts, emptyText }: { alerts: Alert[]; emptyText: string }) {
  if (alerts.length === 0)
    return <EmptyState title="Nothing to worry about" description={emptyText} />;
  return (
    <Stack gap="sm">
      {alerts.map((a) => <AlertRow key={a.id} alert={a} />)}
    </Stack>
  );
}


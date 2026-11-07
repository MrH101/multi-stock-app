import { Alert, Badge, Center, Group, Loader, Stack, Text, Title, type MantineColor } from "@mantine/core";
import { IconAlertTriangle, IconInbox } from "@tabler/icons-react";
import type { ReactNode } from "react";
import { ApiError } from "@/shared/api/http";
import { date, daysUntil } from "@/shared/format";

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <Group justify="space-between" align="flex-end" mb="lg" wrap="wrap" gap="sm">
      <div>
        <Title order={2}>{title}</Title>
        {description && (
          <Text c="dimmed" size="sm" mt={4}>
            {description}
          </Text>
        )}
      </div>
      {actions && <Group gap="sm">{actions}</Group>}
    </Group>
  );
}

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <Center py={48}>
      <Stack align="center" gap="xs" maw={420} ta="center">
        <IconInbox size={40} stroke={1.3} color="var(--mantine-color-gray-5)" />
        <Text fw={600}>{title}</Text>
        {description && (
          <Text c="dimmed" size="sm">
            {description}
          </Text>
        )}
        {action}
      </Stack>
    </Center>
  );
}

export function ErrorNotice({ error, title = "Couldn't load this" }: { error: unknown; title?: string }) {
  const message = error instanceof Error ? error.message : "Unexpected error";
  const problems = error instanceof ApiError ? error.problems : [];
  return (
    <Alert color="red" icon={<IconAlertTriangle size={18} />} title={title} my="sm">
      {message}
      {problems.length > 0 && (
        <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
    </Alert>
  );
}

export function Loading() {
  return (
    <Center py={48}>
      <Loader />
    </Center>
  );
}

export const ORDER_STATUS: Record<string, { label: string; color: MantineColor; help: string }> = {
  SUBMITTED: { label: "Awaiting supplier", color: "blue", help: "Sent to the supplier, waiting for them to accept" },
  ACCEPTED: { label: "Accepted", color: "teal", help: "The supplier is preparing the order" },
  DISPATCHED: { label: "On the way", color: "violet", help: "The order has left the supplier" },
  DELIVERED: { label: "Delivered", color: "green", help: "Received by the pharmacy" },
  REJECTED: { label: "Rejected", color: "red", help: "The supplier could not fulfil the order" },
  CANCELLED: { label: "Cancelled", color: "gray", help: "Cancelled before dispatch" },
};

export function StatusBadge({ status, size = "md" }: { status: string; size?: "sm" | "md" | "lg" }) {
  const s = ORDER_STATUS[status] ?? { label: status, color: "gray" };
  return (
    <Badge color={s.color} variant="light" size={size}>
      {s.label}
    </Badge>
  );
}

/** Red under 90 days, orange under 180, otherwise neutral — pharmacists scan for this. */
export function ExpiryBadge({ expiry }: { expiry: string | null }) {
  if (!expiry) return <Text size="sm" c="dimmed">—</Text>;
  const days = daysUntil(expiry);
  const color = days <= 0 ? "red" : days < 90 ? "red" : days < 180 ? "orange" : "gray";
  const label = days <= 0 ? "Expired" : days < 180 ? `${date(expiry)} · ${days}d` : date(expiry);
  return (
    <Badge color={color} variant={days < 180 ? "light" : "outline"} radius="sm" style={{ textTransform: "none" }}>
      {label}
    </Badge>
  );
}

export function StockBadge({ qty, reorder = 0 }: { qty: number; reorder?: number }) {
  if (qty <= 0) return <Badge color="red" variant="light">Out of stock</Badge>;
  if (reorder && qty <= reorder) return <Badge color="orange" variant="light">Low · {qty}</Badge>;
  return <Badge color="green" variant="light">{qty.toLocaleString()} in stock</Badge>;
}

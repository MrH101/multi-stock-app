import { ActionIcon, Button, Divider, Group, Indicator, Popover, ScrollArea, Stack, Text, UnstyledButton } from "@mantine/core";
import { IconBell } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { fromNow } from "@/shared/format";
import { messagingApi } from "./api";

export function NotificationBell() {
  const [opened, setOpened] = useState(false);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const unread = useQuery({ queryKey: ["unread"], queryFn: messagingApi.unread, refetchInterval: 60_000 });
  const list = useQuery({ queryKey: ["notifications"], queryFn: messagingApi.notifications, enabled: opened });
  const refresh = () => qc.invalidateQueries({ queryKey: ["unread"] }).then(() => qc.invalidateQueries({ queryKey: ["notifications"] }));
  const markRead = useMutation({ mutationFn: messagingApi.markRead, onSuccess: refresh });
  const markAll = useMutation({ mutationFn: messagingApi.markAllRead, onSuccess: refresh });
  const count = unread.data?.notifications ?? 0;

  return (
    <Popover opened={opened} onChange={setOpened} width={360} position="bottom-end" shadow="md">
      <Popover.Target>
        <Indicator label={count > 9 ? "9+" : count} size={16} disabled={!count} color="red" offset={4}>
          <ActionIcon variant="subtle" size="lg" onClick={() => setOpened((o) => !o)} aria-label={`Notifications (${count} unread)`}>
            <IconBell size={20} />
          </ActionIcon>
        </Indicator>
      </Popover.Target>
      <Popover.Dropdown p={0}>
        <Group justify="space-between" p="sm">
          <Text fw={600}>Notifications</Text>
          <Button size="compact-xs" variant="subtle" disabled={!count} onClick={() => markAll.mutate()}>
            Mark all read
          </Button>
        </Group>
        <Divider />
        <ScrollArea.Autosize mah={420}>
          {list.data?.length === 0 && (
            <Text c="dimmed" size="sm" p="md" ta="center">
              You're all caught up.
            </Text>
          )}
          <Stack gap={0}>
            {list.data?.map((n) => (
              <UnstyledButton
                key={n.id}
                p="sm"
                style={{ borderBottom: "1px solid var(--mantine-color-gray-2)", background: n.read ? undefined : "var(--mantine-color-teal-0)" }}
                onClick={() => {
                  if (!n.read) markRead.mutate(n.id);
                  setOpened(false);
                  if (n.link) navigate(n.link);
                }}
              >
                <Text size="sm" fw={n.read ? 400 : 600}>
                  {n.title}
                </Text>
                <Text size="xs" c="dimmed" lineClamp={2}>
                  {n.body}
                </Text>
                <Text size="xs" c="dimmed" mt={2}>
                  {fromNow(n.created_at)}
                </Text>
              </UnstyledButton>
            ))}
          </Stack>
        </ScrollArea.Autosize>
      </Popover.Dropdown>
    </Popover>
  );
}

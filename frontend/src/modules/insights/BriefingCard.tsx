import { ActionIcon, Badge, Button, Card, Group, List, Skeleton, Text, ThemeIcon, Tooltip } from "@mantine/core";
import { IconArrowRight, IconRefresh, IconSparkles } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fromNow } from "@/shared/format";
import { ErrorNotice } from "@/shared/ui";
import { insightsApi } from "./api";

/** The agent's written briefing: what matters today and what to do about it. */
export function BriefingCard({ withLink = false, maxActions = 5 }: { withLink?: boolean; maxActions?: number }) {
  const qc = useQueryClient();
  const digest = useQuery({ queryKey: ["insights", "digest"], queryFn: insightsApi.digest, refetchInterval: 5 * 60_000 });
  const refresh = useMutation({
    mutationFn: insightsApi.refreshDigest,
    onSuccess: (d) => qc.setQueryData(["insights", "digest"], d),
  });
  const d = digest.data;

  return (
    <Card h="100%">
      <Group justify="space-between" mb="xs" wrap="nowrap">
        <Group gap="xs" wrap="nowrap">
          <ThemeIcon variant="light" color="grape" radius="md"><IconSparkles size={18} /></ThemeIcon>
          <Text fw={600}>Today's briefing</Text>
          {d && (
            <Tooltip label={d.generated_by === "ai" ? `Written by the AI assistant (${d.model ?? "model"}) from your live alerts` : "Rule-based summary of your live alerts"}>
              <Badge size="xs" variant="light" color={d.generated_by === "ai" ? "grape" : "gray"}>{d.generated_by === "ai" ? "AI" : "Auto"}</Badge>
            </Tooltip>
          )}
        </Group>
        <Group gap={4} wrap="nowrap">
          {d && <Text size="xs" c="dimmed" visibleFrom="xs">{fromNow(d.created_at)}</Text>}
          <Tooltip label="Rewrite now">
            <ActionIcon variant="subtle" color="gray" loading={refresh.isPending} onClick={() => refresh.mutate()} aria-label="Refresh briefing">
              <IconRefresh size={16} />
            </ActionIcon>
          </Tooltip>
        </Group>
      </Group>
      {digest.isLoading && <Skeleton h={80} />}
      {digest.error && <ErrorNotice error={digest.error} title="Briefing unavailable" />}
      {d && (
        <>
          <Text size="lg" fw={700} lh={1.3}>{d.headline}</Text>
          <Text size="sm" c="dimmed" mt={4}>{d.summary}</Text>
          {d.actions.length > 0 && (
            <List spacing={6} mt="sm" size="sm" listStyleType="none" pl={0}>
              {d.actions.slice(0, maxActions).map((a, i) => (
                <List.Item key={`${a.alert_id}-${i}`}>
                  <Group gap={6} wrap="nowrap" align="flex-start">
                    <Text size="sm" fw={700} c="grape" w={18}>{i + 1}.</Text>
                    <div style={{ flex: 1 }}>
                      {a.link ? (
                        <Text component={Link} to={a.link} size="sm" fw={600} c="inherit" style={{ textDecoration: "none" }}>{a.title} →</Text>
                      ) : (
                        <Text size="sm" fw={600}>{a.title}</Text>
                      )}
                      <Text size="xs" c="dimmed">{a.detail}</Text>
                    </div>
                  </Group>
                </List.Item>
              ))}
            </List>
          )}
          {withLink && (
            <Button component={Link} to="/insights" variant="subtle" size="compact-sm" mt="sm" rightSection={<IconArrowRight size={14} />}>
              All insights & ask the assistant
            </Button>
          )}
        </>
      )}
    </Card>
  );
}

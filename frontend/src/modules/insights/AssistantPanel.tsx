import { ActionIcon, Alert, Badge, Card, Group, Loader, Paper, ScrollArea, Stack, Text, Textarea, ThemeIcon } from "@mantine/core";
import { IconMessageChatbot, IconSend } from "@tabler/icons-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useAccount } from "@/shared/auth/session";
import { insightsApi, type ChatTurn } from "./api";

const SUGGESTIONS = {
  pharmacy: ["How much of my budget is left?", "Which of my orders are still waiting?", "Who has amoxicillin 500mg in stock?"],
  supplier: ["What should I restock this week?", "Which batches expire in the next 60 days?", "Which orders need action?"],
  admin: ["Summarise the open alerts", "How many orders are open right now?"],
};

export function AssistantPanel() {
  const { isPharmacy, isSupplier } = useAccount();
  const status = useQuery({ queryKey: ["insights", "status"], queryFn: insightsApi.status, staleTime: 60_000 });
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const viewport = useRef<HTMLDivElement>(null);
  const ask = useMutation({
    mutationFn: insightsApi.ask,
    onSuccess: (r) => setTurns((t) => [...t, { role: "assistant", content: r.answer }]),
  });

  useEffect(() => {
    viewport.current?.scrollTo({ top: viewport.current.scrollHeight, behavior: "smooth" });
  }, [turns, ask.isPending]);

  const send = (text: string) => {
    const q = text.trim();
    if (!q || ask.isPending) return;
    const next: ChatTurn[] = [...turns, { role: "user", content: q }];
    setTurns(next);
    setDraft("");
    ask.mutate(next.slice(-12));
  };

  const suggestions = isPharmacy ? SUGGESTIONS.pharmacy : isSupplier ? SUGGESTIONS.supplier : SUGGESTIONS.admin;
  const offline = status.data && !status.data.ai_enabled;

  return (
    <Card p={0} h="100%" style={{ display: "flex", flexDirection: "column" }}>
      <Group p="md" gap="xs" style={{ borderBottom: "1px solid var(--mantine-color-gray-2)" }}>
        <ThemeIcon variant="light" color="teal" radius="md"><IconMessageChatbot size={18} /></ThemeIcon>
        <Text fw={600}>Ask the assistant</Text>
        <Badge size="xs" variant="light" color="gray">Read-only</Badge>
      </Group>
      <ScrollArea h={380} viewportRef={viewport} px="md" py="sm" style={{ flex: 1 }}>
        {offline && <Alert color="gray" mb="sm">The assistant isn't switched on for this installation yet. Alerts and briefings still work.</Alert>}
        {turns.length === 0 && !offline && (
          <Stack gap="xs">
            <Text size="sm" c="dimmed">Ask about your stock, orders, budget or alerts. It looks up live data you have access to.</Text>
            {suggestions.map((s) => (
              <Paper key={s} p="xs" radius="md" style={{ cursor: "pointer" }} onClick={() => send(s)}>
                <Text size="sm">{s}</Text>
              </Paper>
            ))}
          </Stack>
        )}
        <Stack gap="sm">
          {turns.map((t, i) => (
            <Paper key={i} p="sm" radius="md" maw="88%" ml={t.role === "user" ? "auto" : 0}
              bg={t.role === "user" ? "teal.0" : "white"} withBorder={t.role !== "user"}>
              <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{t.content}</Text>
            </Paper>
          ))}
          {ask.isPending && <Group gap="xs"><Loader size="xs" /><Text size="sm" c="dimmed">Looking that up…</Text></Group>}
          {ask.error && <Alert color="red" variant="light">{ask.error.message}</Alert>}
        </Stack>
      </ScrollArea>
      <Group p="sm" gap="xs" wrap="nowrap" style={{ borderTop: "1px solid var(--mantine-color-gray-2)" }}>
        <Textarea
          style={{ flex: 1 }}
          autosize
          minRows={1}
          maxRows={4}
          placeholder="Type a question…"
          value={draft}
          disabled={!!offline}
          onChange={(e) => setDraft(e.currentTarget.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(draft);
            }
          }}
        />
        <ActionIcon size="lg" onClick={() => send(draft)} disabled={!draft.trim() || ask.isPending || !!offline} aria-label="Send question">
          <IconSend size={18} />
        </ActionIcon>
      </Group>
      <Text size="xs" c="dimmed" px="md" pb="sm">Not for clinical or dosing advice. Always check important figures in the app.</Text>
    </Card>
  );
}

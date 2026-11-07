import { Badge, Box, Button, Card, Grid, Group, ScrollArea, Stack, Text, Textarea, UnstyledButton } from "@mantine/core";
import { IconArrowLeft, IconSend } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAccount } from "@/shared/auth/session";
import { dateTime, fromNow } from "@/shared/format";
import { EmptyState, ErrorNotice, Loading, PageHeader } from "@/shared/ui";
import { messagingApi } from "./api";

export default function MessagesPage() {
  const { conversationId } = useParams();
  const selected = conversationId ? Number(conversationId) : null;
  const navigate = useNavigate();
  const { isPharmacy } = useAccount();
  const convs = useQuery({ queryKey: ["conversations"], queryFn: messagingApi.conversations });

  return (
    <>
      <PageHeader
        title="Messages"
        description={isPharmacy ? "Ask suppliers about availability, prices and deliveries." : "Questions from pharmacies."}
        actions={<Button component={Link} to={isPharmacy ? "/suppliers" : "/pharmacies"} variant="light">New message</Button>}
      />
      {convs.error && <ErrorNotice error={convs.error} />}
      <Grid>
        <Grid.Col span={{ base: 12, md: 4 }} display={{ base: selected ? "none" : "block", md: "block" }}>
          <Card p={0}>
            {convs.isLoading && <Loading />}
            {convs.data?.length === 0 && <EmptyState title="No conversations yet" description={`Start one from the ${isPharmacy ? "Suppliers" : "Pharmacies"} page or from an order.`} />}
            {convs.data?.map((c) => (
              <UnstyledButton key={c.id} onClick={() => navigate(`/messages/${c.id}`)} w="100%" p="md"
                style={{ borderBottom: "1px solid var(--mantine-color-gray-2)", background: c.id === selected ? "var(--mantine-color-teal-0)" : undefined }}>
                <Group justify="space-between" wrap="nowrap">
                  <Text fw={600} size="sm" truncate>{c.counterpart_name}</Text>
                  {c.unread > 0 && <Badge size="sm" color="red" circle>{c.unread}</Badge>}
                </Group>
                <Text size="sm" truncate>{c.subject}{c.order_number && ` · ${c.order_number}`}</Text>
                <Text size="xs" c="dimmed" truncate>{c.last_message_preview}</Text>
                {c.last_message_at && <Text size="xs" c="dimmed">{fromNow(c.last_message_at)}</Text>}
              </UnstyledButton>
            ))}
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 8 }} display={{ base: selected ? "block" : "none", md: "block" }}>
          {selected ? <Thread id={selected} /> : <Card><EmptyState title="Select a conversation" /></Card>}
        </Grid.Col>
      </Grid>
    </>
  );
}

function Thread({ id }: { id: number }) {
  const qc = useQueryClient();
  const { organization } = useAccount();
  const [body, setBody] = useState("");
  const viewport = useRef<HTMLDivElement>(null);
  const conv = useQuery({ queryKey: ["conversations"], queryFn: messagingApi.conversations, select: (all) => all.find((c) => c.id === id) });
  const messages = useQuery({ queryKey: ["conversations", id, "messages"], queryFn: () => messagingApi.messages(id) });
  const send = useMutation({
    mutationFn: () => messagingApi.send(id, body.trim()),
    onSuccess: () => {
      setBody("");
      qc.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  useEffect(() => {
    qc.invalidateQueries({ queryKey: ["unread"] });
    viewport.current?.scrollTo({ top: viewport.current.scrollHeight });
  }, [messages.data, qc]);

  return (
    <Card p={0}>
      <Group p="md" style={{ borderBottom: "1px solid var(--mantine-color-gray-2)" }}>
        <Button component={Link} to="/messages" variant="subtle" size="compact-sm" hiddenFrom="md" leftSection={<IconArrowLeft size={14} />}>Back</Button>
        <div>
          <Text fw={600}>{conv.data?.subject}</Text>
          <Text size="xs" c="dimmed">with {conv.data?.counterpart_name}{conv.data?.order_number && ` · about ${conv.data.order_number}`}</Text>
        </div>
      </Group>
      <ScrollArea h={440} viewportRef={viewport} p="md">
        {messages.isLoading && <Loading />}
        <Stack gap="sm">
          {messages.data?.map((m) => {
            const mine = m.sender_org_id === organization?.id;
            return (
              <Box key={m.id} maw="80%" ml={mine ? "auto" : 0} p="sm" style={{ borderRadius: 10, background: mine ? "var(--mantine-color-teal-1)" : "var(--mantine-color-gray-1)" }}>
                <Text size="xs" c="dimmed">{m.sender_name} · {dateTime(m.created_at)}</Text>
                <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{m.body}</Text>
              </Box>
            );
          })}
        </Stack>
      </ScrollArea>
      <form onSubmit={(e) => { e.preventDefault(); if (body.trim()) send.mutate(); }}>
        <Group p="md" align="flex-end" style={{ borderTop: "1px solid var(--mantine-color-gray-2)" }} wrap="nowrap">
          <Textarea flex={1} autosize minRows={1} maxRows={5} placeholder="Type a message… (Enter to send, Shift+Enter for a new line)" value={body}
            onChange={(e) => setBody(e.currentTarget.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (body.trim()) send.mutate(); } }} />
          <Button type="submit" loading={send.isPending} leftSection={<IconSend size={16} />}>Send</Button>
        </Group>
        {send.error && <Box px="md" pb="md"><ErrorNotice error={send.error} title="Not sent" /></Box>}
      </form>
    </Card>
  );
}

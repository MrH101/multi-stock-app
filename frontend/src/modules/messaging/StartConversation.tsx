import { Button, Group, Stack, Textarea, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { modals } from "@mantine/modals";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ErrorNotice } from "@/shared/ui";
import { messagingApi } from "./api";

interface Props {
  orgId: number;
  orgName: string;
  subject?: string;
  orderNumber?: string;
  onCreated?: (conversationId: number) => void;
}

function StartConversationForm({ orgId, orgName, subject = "", orderNumber, onCreated }: Props) {
  const qc = useQueryClient();
  const form = useForm({
    initialValues: { subject, body: "" },
    validate: { subject: (v) => (v.trim().length >= 2 ? null : "Add a short subject"), body: (v) => (v.trim() ? null : "Write a message") },
  });
  const start = useMutation({
    mutationFn: (v: typeof form.values) =>
      messagingApi.startConversation({ counterpart_org_id: orgId, counterpart_org_name: orgName, subject: v.subject, body: v.body, order_number: orderNumber }),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      modals.closeAll();
      onCreated?.(c.id);
    },
  });
  return (
    <form onSubmit={form.onSubmit((v) => start.mutate(v))}>
      <Stack>
        {start.error && <ErrorNotice error={start.error} title="Message not sent" />}
        <TextInput label="Subject" required {...form.getInputProps("subject")} />
        <Textarea label="Message" required autosize minRows={4} autoFocus {...form.getInputProps("body")} />
        <Group justify="flex-end">
          <Button variant="default" onClick={() => modals.closeAll()}>Cancel</Button>
          <Button type="submit" loading={start.isPending}>Send</Button>
        </Group>
      </Stack>
    </form>
  );
}

export function openStartConversation(props: Props) {
  modals.open({ title: `Message ${props.orgName}`, size: "lg", children: <StartConversationForm {...props} /> });
}

import { Badge, Button, Card, Group, Select, Stack, Text, Textarea, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAccount } from "@/shared/auth/session";
import { dateTime } from "@/shared/format";
import { EmptyState, ErrorNotice, Loading, PageHeader } from "@/shared/ui";
import { messagingApi, type Broadcast } from "./api";

export default function AnnouncementsPage() {
  const { isPharmacy, isAdmin, canManage } = useAccount();
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["broadcasts"], queryFn: messagingApi.broadcasts });
  const form = useForm({
    initialValues: { title: "", body: "", audience: "PHARMACIES" as Broadcast["audience"] },
    validate: { title: (v) => (v.trim().length >= 2 ? null : "Required"), body: (v) => (v.trim().length >= 2 ? null : "Required") },
  });
  const create = useMutation({
    mutationFn: messagingApi.createBroadcast,
    onSuccess: () => {
      form.reset();
      qc.invalidateQueries({ queryKey: ["broadcasts"] });
      notifications.show({ color: "teal", message: "Announcement published" });
    },
  });
  const canPost = !isPharmacy && canManage;

  return (
    <>
      <PageHeader title="Announcements" description={isPharmacy ? "Price changes, new stock and notices from suppliers." : "Tell pharmacies about new stock, price changes or delivery schedules."} />
      {canPost && (
        <Card mb="lg">
          <Title order={5} mb="sm">New announcement</Title>
          <form onSubmit={form.onSubmit((v) => create.mutate(v))}>
            <Stack>
              {create.error && <ErrorNotice error={create.error} title="Not published" />}
              <TextInput label="Title" placeholder="e.g. Amoxicillin 500mg back in stock" {...form.getInputProps("title")} />
              <Textarea label="Details" autosize minRows={3} {...form.getInputProps("body")} />
              {isAdmin && <Select label="Audience" allowDeselect={false} data={[{ value: "ALL", label: "Everyone" }, { value: "PHARMACIES", label: "Pharmacies" }, { value: "SUPPLIERS", label: "Suppliers" }]} {...form.getInputProps("audience")} />}
              <Group justify="flex-end"><Button type="submit" loading={create.isPending}>Publish</Button></Group>
            </Stack>
          </form>
        </Card>
      )}
      {list.isLoading && <Loading />}
      {list.error && <ErrorNotice error={list.error} />}
      {list.data?.length === 0 && <EmptyState title="No announcements yet" />}
      <Stack>
        {list.data?.map((b) => (
          <Card key={b.id}>
            <Group justify="space-between">
              <Text fw={600}>{b.title}</Text>
              <Badge variant="light" color={b.sender_org_type === "PLATFORM" ? "violet" : "teal"}>{b.sender_org_name}</Badge>
            </Group>
            <Text size="sm" mt="xs" style={{ whiteSpace: "pre-wrap" }}>{b.body}</Text>
            <Text size="xs" c="dimmed" mt="xs">{dateTime(b.created_at)}</Text>
          </Card>
        ))}
      </Stack>
    </>
  );
}

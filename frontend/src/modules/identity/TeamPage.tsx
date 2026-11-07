import { Badge, Button, Card, Group, Modal, PasswordInput, Select, Stack, Switch, Table, Text, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconUserPlus } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Role } from "@/shared/auth/session";
import { useAccount } from "@/shared/auth/session";
import { date } from "@/shared/format";
import { ErrorNotice, Loading, PageHeader } from "@/shared/ui";
import { identityApi } from "./api";

const ROLES = [
  { value: "STAFF", label: "Staff — places / processes orders" },
  { value: "MANAGER", label: "Manager — also sets budgets & products" },
  { value: "OWNER", label: "Owner — also manages the team" },
];

export default function TeamPage() {
  const { isOwner, user: me } = useAccount();
  const qc = useQueryClient();
  const team = useQuery({ queryKey: ["team"], queryFn: identityApi.team });
  const [opened, { open, close }] = useDisclosure();
  const form = useForm({
    initialValues: { full_name: "", email: "", phone: "", role: "STAFF" as Role, password: "" },
    validate: {
      full_name: (v) => (v.length >= 2 ? null : "Required"),
      email: (v) => (/^\S+@\S+\.\S+$/.test(v) ? null : "Enter a valid email"),
      password: (v) => (v.length >= 8 ? null : "At least 8 characters"),
    },
  });
  const add = useMutation({
    mutationFn: identityApi.addMember,
    onSuccess: (u) => {
      qc.invalidateQueries({ queryKey: ["team"] });
      notifications.show({ color: "teal", message: `${u.full_name} can now sign in with ${u.email}` });
      form.reset();
      close();
    },
  });
  const update = useMutation({
    mutationFn: ({ id, ...body }: { id: number; role?: Role; is_active?: boolean }) => identityApi.updateMember(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["team"] }),
    onError: (e) => notifications.show({ color: "red", message: e.message }),
  });

  return (
    <>
      <PageHeader
        title="Team"
        description="Everyone in your organisation who can sign in."
        actions={isOwner && <Button leftSection={<IconUserPlus size={18} />} onClick={open}>Add team member</Button>}
      />
      <Card p={0}>
        {team.isLoading && <Loading />}
        {team.error && <ErrorNotice error={team.error} />}
        <Table.ScrollContainer minWidth={640}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Name</Table.Th>
                <Table.Th>Email</Table.Th>
                <Table.Th>Role</Table.Th>
                <Table.Th>Since</Table.Th>
                <Table.Th>Active</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {team.data?.map((u) => (
                <Table.Tr key={u.id}>
                  <Table.Td fw={500}>{u.full_name}{u.id === me?.id && <Badge ml="xs" size="xs" variant="light">You</Badge>}</Table.Td>
                  <Table.Td>{u.email}</Table.Td>
                  <Table.Td w={220}>
                    {isOwner && u.id !== me?.id ? (
                      <Select size="xs" data={ROLES.map((r) => ({ value: r.value, label: r.value.charAt(0) + r.value.slice(1).toLowerCase() }))} value={u.role}
                        onChange={(role) => role && update.mutate({ id: u.id, role: role as Role })} allowDeselect={false} />
                    ) : (
                      <Badge variant="outline">{u.role.toLowerCase()}</Badge>
                    )}
                  </Table.Td>
                  <Table.Td>{date(u.created_at)}</Table.Td>
                  <Table.Td>
                    <Switch checked={u.is_active} disabled={!isOwner || u.id === me?.id} onChange={(e) => update.mutate({ id: u.id, is_active: e.currentTarget.checked })} aria-label="Active" />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      <Modal opened={opened} onClose={close} title="Add team member">
        <form onSubmit={form.onSubmit((v) => add.mutate(v))}>
          <Stack>
            {add.error && <ErrorNotice error={add.error} title="Could not add" />}
            <TextInput label="Full name" required {...form.getInputProps("full_name")} />
            <TextInput label="Email" type="email" required {...form.getInputProps("email")} />
            <TextInput label="Phone" {...form.getInputProps("phone")} />
            <Select label="Role" data={ROLES} allowDeselect={false} {...form.getInputProps("role")} />
            <PasswordInput label="Temporary password" required description="Share it with them; they can change it in Settings." {...form.getInputProps("password")} />
            <Group justify="flex-end">
              <Button variant="default" onClick={close}>Cancel</Button>
              <Button type="submit" loading={add.isPending}>Add member</Button>
            </Group>
          </Stack>
        </form>
      </Modal>
      {!isOwner && <Text size="sm" c="dimmed" mt="sm">Only the account owner can add or change team members.</Text>}
    </>
  );
}

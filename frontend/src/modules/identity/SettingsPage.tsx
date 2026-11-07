import { Badge, Button, Card, Grid, Group, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useMutation } from "@tanstack/react-query";
import { useAccount, useSession } from "@/shared/auth/session";
import { PaymentSettings } from "@/modules/payments/PaymentSettings";
import { ErrorNotice, PageHeader } from "@/shared/ui";
import { identityApi } from "./api";

export default function SettingsPage() {
  const { organization, user, canManage, isSupplier } = useAccount();
  const setOrganization = useSession((s) => s.setOrganization);
  const org = useForm({
    initialValues: { name: organization?.name ?? "", email: organization?.email ?? "", phone: organization?.phone ?? "", address: organization?.address ?? "", city: organization?.city ?? "" },
  });
  const saveOrg = useMutation({
    mutationFn: identityApi.updateMyOrg,
    onSuccess: (o) => {
      setOrganization(o);
      notifications.show({ color: "teal", message: "Organisation details saved" });
    },
  });
  const pw = useForm({
    initialValues: { current: "", next: "", confirm: "" },
    validate: { next: (v) => (v.length >= 8 ? null : "At least 8 characters"), confirm: (v, a) => (v === a.next ? null : "Passwords do not match") },
  });
  const changePw = useMutation({
    mutationFn: (v: typeof pw.values) => identityApi.changePassword(v.current, v.next),
    onSuccess: () => {
      pw.reset();
      notifications.show({ color: "teal", message: "Password changed" });
    },
  });

  return (
    <>
      <PageHeader title="Settings" />
      <Grid>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Card>
            <Group justify="space-between" mb="md">
              <Title order={4}>Organisation</Title>
              <Badge color={organization?.verified ? "green" : "yellow"} variant="light">
                {organization?.verified ? "Verified" : "Verification pending"}
              </Badge>
            </Group>
            <Text size="sm" c="dimmed" mb="md">Licence: {organization?.license_number ?? "—"}</Text>
            <form onSubmit={org.onSubmit((v) => saveOrg.mutate(v))}>
              <Stack>
                {saveOrg.error && <ErrorNotice error={saveOrg.error} title="Could not save" />}
                <TextInput label="Name" disabled={!canManage} {...org.getInputProps("name")} />
                <Group grow>
                  <TextInput label="Email" disabled={!canManage} {...org.getInputProps("email")} />
                  <TextInput label="Phone" disabled={!canManage} {...org.getInputProps("phone")} />
                </Group>
                <TextInput label="Address (used as default delivery address)" disabled={!canManage} {...org.getInputProps("address")} />
                <TextInput label="City / town" disabled={!canManage} {...org.getInputProps("city")} />
                {canManage && <Group justify="flex-end"><Button type="submit" loading={saveOrg.isPending}>Save</Button></Group>}
              </Stack>
            </form>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Card>
            <Title order={4} mb={4}>Your account</Title>
            <Text size="sm" c="dimmed" mb="md">{user?.full_name} · {user?.email}</Text>
            <form onSubmit={pw.onSubmit((v) => changePw.mutate(v))}>
              <Stack>
                {changePw.error && <ErrorNotice error={changePw.error} title="Could not change password" />}
                <PasswordInput label="Current password" required {...pw.getInputProps("current")} />
                <PasswordInput label="New password" required {...pw.getInputProps("next")} />
                <PasswordInput label="Confirm new password" required {...pw.getInputProps("confirm")} />
                <Group justify="flex-end"><Button type="submit" loading={changePw.isPending}>Change password</Button></Group>
              </Stack>
            </form>
          </Card>
        </Grid.Col>
        {isSupplier && canManage && <Grid.Col span={12}><PaymentSettings /></Grid.Col>}
      </Grid>
    </>
  );
}

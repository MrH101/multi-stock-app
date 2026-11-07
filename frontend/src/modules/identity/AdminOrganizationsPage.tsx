import { Badge, Button, Card, Group, SegmentedControl, Table, TextInput } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { modals } from "@mantine/modals";
import { IconSearch } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { OrgType } from "@/shared/auth/session";
import { date } from "@/shared/format";
import { ErrorNotice, Loading, PageHeader } from "@/shared/ui";
import { identityApi } from "./api";

export default function AdminOrganizationsPage() {
  const [type, setType] = useState<"ALL" | OrgType>("ALL");
  const [q, setQ] = useState("");
  const [debounced] = useDebouncedValue(q, 250);
  const qc = useQueryClient();
  const orgs = useQuery({
    queryKey: ["organizations", "admin", type, debounced],
    queryFn: () => identityApi.organizations({ type: type === "ALL" ? undefined : type, q: debounced }),
  });
  const update = useMutation({
    mutationFn: ({ id, ...body }: { id: number; verified?: boolean; is_active?: boolean }) => identityApi.adminUpdateOrg(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["organizations"] }),
  });

  return (
    <>
      <PageHeader title="Organisations" description="Verify licences and manage access for pharmacies and suppliers." />
      <Group mb="md">
        <SegmentedControl value={type} onChange={(v) => setType(v as typeof type)} data={[{ value: "ALL", label: "All" }, { value: "PHARMACY", label: "Pharmacies" }, { value: "SUPPLIER", label: "Suppliers" }]} />
        <TextInput leftSection={<IconSearch size={16} />} placeholder="Search" value={q} onChange={(e) => setQ(e.currentTarget.value)} />
      </Group>
      {update.error && <ErrorNotice error={update.error} />}
      <Card p={0}>
        {orgs.isLoading && <Loading />}
        <Table.ScrollContainer minWidth={800}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Name</Table.Th><Table.Th>Type</Table.Th><Table.Th>Licence</Table.Th><Table.Th>City</Table.Th><Table.Th>Joined</Table.Th><Table.Th>Status</Table.Th><Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {orgs.data?.map((o) => (
                <Table.Tr key={o.id}>
                  <Table.Td fw={500}>{o.name}</Table.Td>
                  <Table.Td><Badge variant="outline">{o.type.toLowerCase()}</Badge></Table.Td>
                  <Table.Td>{o.license_number}</Table.Td>
                  <Table.Td>{o.city ?? "—"}</Table.Td>
                  <Table.Td>{date(o.created_at)}</Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      <Badge color={o.verified ? "green" : "yellow"} variant="light">{o.verified ? "Verified" : "Unverified"}</Badge>
                      {!o.is_active && <Badge color="red" variant="light">Suspended</Badge>}
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    <Group gap="xs" justify="flex-end" wrap="nowrap">
                      <Button size="xs" variant={o.verified ? "default" : "filled"} onClick={() => update.mutate({ id: o.id, verified: !o.verified })}>
                        {o.verified ? "Unverify" : "Verify licence"}
                      </Button>
                      <Button size="xs" variant="subtle" color={o.is_active ? "red" : "teal"}
                        onClick={() => modals.openConfirmModal({
                          title: o.is_active ? `Suspend ${o.name}?` : `Reactivate ${o.name}?`,
                          children: o.is_active ? "Their users will not be able to sign in." : "Their users will be able to sign in again.",
                          labels: { confirm: o.is_active ? "Suspend" : "Reactivate", cancel: "Cancel" },
                          confirmProps: { color: o.is_active ? "red" : "teal" },
                          onConfirm: () => update.mutate({ id: o.id, is_active: !o.is_active }),
                        })}>
                        {o.is_active ? "Suspend" : "Reactivate"}
                      </Button>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
    </>
  );
}

import { Badge, Button, Card, Group, SimpleGrid, Stack, Text, TextInput } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconMapPin, IconMessage, IconPhone, IconSearch } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { openStartConversation } from "@/modules/messaging/StartConversation";
import type { OrgType } from "@/shared/auth/session";
import { EmptyState, ErrorNotice, Loading, PageHeader } from "@/shared/ui";
import { identityApi } from "./api";

export default function DirectoryPage({ type }: { type: Exclude<OrgType, "PLATFORM"> }) {
  const [q, setQ] = useState("");
  const [debounced] = useDebouncedValue(q, 250);
  const navigate = useNavigate();
  const orgs = useQuery({ queryKey: ["organizations", type, debounced], queryFn: () => identityApi.organizations({ type, q: debounced }) });
  const isSuppliers = type === "SUPPLIER";

  return (
    <>
      <PageHeader title={isSuppliers ? "Suppliers" : "Pharmacies"} description={isSuppliers ? "Licensed wholesalers you can order from." : "Pharmacies on the platform."} />
      <TextInput leftSection={<IconSearch size={16} />} placeholder="Search by name" value={q} onChange={(e) => setQ(e.currentTarget.value)} mb="md" maw={400} />
      {orgs.isLoading && <Loading />}
      {orgs.error && <ErrorNotice error={orgs.error} />}
      {orgs.data?.length === 0 && <EmptyState title="No matches" />}
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
        {orgs.data?.map((o) => (
          <Card key={o.id}>
            <Stack gap={6}>
              <Group justify="space-between" wrap="nowrap">
                <Text fw={600}>{o.name}</Text>
                {o.verified && <Badge color="green" variant="light" size="sm">Verified</Badge>}
              </Group>
              <Text size="sm" c="dimmed">Licence {o.license_number}</Text>
              {(o.city || o.address) && <Group gap={4}><IconMapPin size={14} /><Text size="sm">{[o.address, o.city].filter(Boolean).join(", ")}</Text></Group>}
              {o.phone && <Group gap={4}><IconPhone size={14} /><Text size="sm">{o.phone}</Text></Group>}
              <Group mt="sm" gap="xs">
                {isSuppliers && <Button size="xs" onClick={() => navigate(`/catalog?supplier=${o.id}&supplierName=${encodeURIComponent(o.name)}`)}>View products</Button>}
                <Button size="xs" variant="light" leftSection={<IconMessage size={14} />} onClick={() => openStartConversation({ orgId: o.id, orgName: o.name, onCreated: (id) => navigate(`/messages/${id}`) })}>
                  Message
                </Button>
              </Group>
            </Stack>
          </Card>
        ))}
      </SimpleGrid>
    </>
  );
}

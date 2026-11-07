import { Card, Group, Pagination, Table, Tabs, Text, TextInput } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconSearch } from "@tabler/icons-react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAccount } from "@/shared/auth/session";
import { dateTime, money } from "@/shared/format";
import { EmptyState, ErrorNotice, Loading, PageHeader, StatusBadge } from "@/shared/ui";
import { ordersApi, type OrderStatus } from "./api";

export default function OrdersPage() {
  const { isPharmacy, isSupplier } = useAccount();
  const tabs: { value: string; label: string; status: OrderStatus[] }[] = isSupplier
    ? [
        { value: "new", label: "New — needs action", status: ["SUBMITTED"] },
        { value: "fulfil", label: "To dispatch", status: ["ACCEPTED"] },
        { value: "transit", label: "On the way", status: ["DISPATCHED"] },
        { value: "done", label: "Completed", status: ["DELIVERED", "REJECTED", "CANCELLED"] },
        { value: "all", label: "All", status: [] },
      ]
    : [
        { value: "open", label: "Open", status: ["SUBMITTED", "ACCEPTED", "DISPATCHED"] },
        { value: "done", label: "Completed", status: ["DELIVERED", "REJECTED", "CANCELLED"] },
        { value: "all", label: "All", status: [] },
      ];
  const [tab, setTab] = useState(tabs[0].value);
  const [q, setQ] = useState("");
  const [debounced] = useDebouncedValue(q, 250);
  const [page, setPage] = useState(1);
  const navigate = useNavigate();
  const status = tabs.find((t) => t.value === tab)!.status;
  const orders = useQuery({
    queryKey: ["orders", tab, debounced, page],
    queryFn: () => ordersApi.list({ status, q: debounced, page }),
    placeholderData: keepPreviousData,
  });
  const pages = orders.data ? Math.ceil(orders.data.total / orders.data.page_size) : 0;

  return (
    <>
      <PageHeader title={isPharmacy ? "My orders" : isSupplier ? "Incoming orders" : "All orders"} />
      <Group justify="space-between" mb="md" wrap="wrap">
        <Tabs value={tab} onChange={(v) => { setTab(v!); setPage(1); }}>
          <Tabs.List>{tabs.map((t) => <Tabs.Tab key={t.value} value={t.value}>{t.label}</Tabs.Tab>)}</Tabs.List>
        </Tabs>
        <TextInput leftSection={<IconSearch size={16} />} placeholder="Order number or name" value={q} onChange={(e) => { setQ(e.currentTarget.value); setPage(1); }} w={260} />
      </Group>
      {orders.error && <ErrorNotice error={orders.error} />}
      <Card p={0}>
        {orders.isLoading ? <Loading /> : orders.data?.items.length === 0 ? <EmptyState title="No orders here" /> : (
          <Table.ScrollContainer minWidth={760}>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Order</Table.Th>
                  <Table.Th>{isPharmacy ? "Supplier" : "Pharmacy"}</Table.Th>
                  <Table.Th>Placed</Table.Th>
                  <Table.Th ta="right">Items</Table.Th>
                  <Table.Th ta="right">Value</Table.Th>
                  <Table.Th>Status</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {orders.data?.items.map((o) => (
                  <Table.Tr key={o.id} style={{ cursor: "pointer" }} onClick={() => navigate(`/orders/${o.id}`)}>
                    <Table.Td fw={600}>{o.order_number}</Table.Td>
                    <Table.Td>{isPharmacy ? o.supplier_name : o.pharmacy_name}{!isPharmacy && !isSupplier && <Text size="xs" c="dimmed">→ {o.supplier_name}</Text>}</Table.Td>
                    <Table.Td><Text size="sm">{dateTime(o.created_at)}</Text><Text size="xs" c="dimmed">by {o.created_by_name}</Text></Table.Td>
                    <Table.Td ta="right">{o.item_count}</Table.Td>
                    <Table.Td ta="right" fw={600}>{money(o.subtotal, o.currency)}</Table.Td>
                    <Table.Td><StatusBadge status={o.status} /></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Card>
      {pages > 1 && <Group justify="flex-end" mt="md"><Pagination value={page} onChange={setPage} total={pages} /></Group>}
    </>
  );
}

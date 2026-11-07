import { Badge, Button, Card, Modal, Table, Text, TextInput } from "@mantine/core";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconPlus, IconSearch } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAccount } from "@/shared/auth/session";
import { DOSAGE_FORMS, money } from "@/shared/format";
import { EmptyState, ErrorNotice, ExpiryBadge, Loading, PageHeader, StockBadge } from "@/shared/ui";
import { catalogApi } from "./api";
import { ProductForm } from "./ProductForm";

export default function InventoryPage() {
  const [q, setQ] = useState("");
  const [debounced] = useDebouncedValue(q, 250);
  const [opened, { open, close }] = useDisclosure();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { canManage } = useAccount();
  const products = useQuery({ queryKey: ["my-products", debounced], queryFn: () => catalogApi.myProducts({ q: debounced }) });
  const create = useMutation({
    mutationFn: catalogApi.createProduct,
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["my-products"] });
      close();
      notifications.show({ color: "teal", title: "Product added", message: "Now receive a batch so pharmacies can order it." });
      navigate(`/inventory/${p.id}`);
    },
  });

  return (
    <>
      <PageHeader title="Products & stock" description="Your catalogue. Stock is tracked per batch and expiry date."
        actions={canManage && <Button leftSection={<IconPlus size={18} />} onClick={open}>Add product</Button>} />
      <TextInput leftSection={<IconSearch size={16} />} placeholder="Search your products" value={q} onChange={(e) => setQ(e.currentTarget.value)} mb="md" maw={400} />
      {products.error && <ErrorNotice error={products.error} />}
      <Card p={0}>
        {products.isLoading ? <Loading /> : products.data?.items.length === 0 ? (
          <EmptyState title="No products yet" description="Add your first product, then receive stock against it." action={canManage && <Button onClick={open}>Add product</Button>} />
        ) : (
          <Table.ScrollContainer minWidth={860}>
            <Table>
              <Table.Thead>
                <Table.Tr><Table.Th>Product</Table.Th><Table.Th>Form / pack</Table.Th><Table.Th ta="right">Price</Table.Th><Table.Th>Sellable stock</Table.Th><Table.Th>Earliest expiry</Table.Th><Table.Th>Status</Table.Th></Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {products.data?.items.map((p) => (
                  <Table.Tr key={p.id} style={{ cursor: "pointer" }} onClick={() => navigate(`/inventory/${p.id}`)}>
                    <Table.Td><Text fw={600} size="sm">{p.name} {p.strength}</Text><Text size="xs" c="dimmed">{p.generic_name}{p.sku && ` · ${p.sku}`}</Text></Table.Td>
                    <Table.Td><Text size="sm">{DOSAGE_FORMS[p.dosage_form]}</Text><Text size="xs" c="dimmed">{p.pack_size}</Text></Table.Td>
                    <Table.Td ta="right">{money(p.unit_price, p.currency)}</Table.Td>
                    <Table.Td><StockBadge qty={p.stock_available} reorder={p.reorder_level} /></Table.Td>
                    <Table.Td><ExpiryBadge expiry={p.nearest_expiry} /></Table.Td>
                    <Table.Td>{p.is_active ? <Badge variant="light" color="green">Listed</Badge> : <Badge variant="light" color="gray">Hidden</Badge>}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Card>
      <Modal opened={opened} onClose={close} title="Add product" size="xl">
        <ProductForm onSubmit={(v) => create.mutate(v)} submitting={create.isPending} error={create.error} submitLabel="Add product" />
      </Modal>
    </>
  );
}

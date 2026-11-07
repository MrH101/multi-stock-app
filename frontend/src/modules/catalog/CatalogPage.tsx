import { ActionIcon, Badge, Button, Card, CloseButton, Drawer, Group, NumberInput, Pagination, Select, Stack, Switch, Table, Text, TextInput, Title } from "@mantine/core";
import { useDebouncedValue, useHotkeys } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconInfoCircle, IconSearch, IconShoppingCartPlus } from "@tabler/icons-react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useCart } from "@/modules/orders/cart";
import { DOSAGE_FORMS, SCHEDULES, SCHEDULE_BADGE, date, money, options } from "@/shared/format";
import { EmptyState, ErrorNotice, ExpiryBadge, Loading, PageHeader, StockBadge } from "@/shared/ui";
import { catalogApi, type Product } from "./api";

export default function CatalogPage() {
  const [params, setParams] = useSearchParams();
  const supplierId = params.get("supplier") ? Number(params.get("supplier")) : undefined;
  const supplierName = params.get("supplierName");
  const [q, setQ] = useState(params.get("q") ?? "");
  const [debounced] = useDebouncedValue(q, 250);
  const [form, setForm] = useState<string | null>(null);
  const [inStock, setInStock] = useState(true);
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState<number | null>(null);
  const search = useRef<HTMLInputElement>(null);
  useHotkeys([["/", () => search.current?.focus()]]);

  const results = useQuery({
    queryKey: ["catalog", debounced, form, inStock, supplierId, page],
    queryFn: () => catalogApi.search({ q: debounced, dosage_form: form, in_stock: inStock, supplier_org_id: supplierId, page, page_size: 25 }),
    placeholderData: keepPreviousData,
  });
  const pages = results.data ? Math.ceil(results.data.total / results.data.page_size) : 0;

  return (
    <>
      <PageHeader title="Order medicines" description="Search every supplier at once. Add quantities, then review your cart." actions={<Button component={Link} to="/cart" variant="light">Review cart</Button>} />
      <Card mb="md" p="md">
        <Group align="flex-end" wrap="wrap">
          <TextInput ref={search} autoFocus flex={1} miw={260} size="md" leftSection={<IconSearch size={18} />}
            placeholder="Search by brand, generic name or manufacturer   ( / )" value={q}
            onChange={(e) => { setQ(e.currentTarget.value); setPage(1); }}
            rightSection={q && <CloseButton onClick={() => setQ("")} aria-label="Clear search" />} />
          <Select size="md" w={210} placeholder="All dosage forms" data={options(DOSAGE_FORMS)} value={form} onChange={(v) => { setForm(v); setPage(1); }} clearable />
          <Switch size="md" label="In stock only" checked={inStock} onChange={(e) => { setInStock(e.currentTarget.checked); setPage(1); }} />
        </Group>
        {supplierId && (
          <Group mt="sm" gap="xs">
            <Text size="sm">Showing products from</Text>
            <Badge size="lg" variant="light" rightSection={<CloseButton size="xs" onClick={() => setParams({})} aria-label="Show all suppliers" />}>
              {supplierName ?? `supplier #${supplierId}`}
            </Badge>
          </Group>
        )}
      </Card>

      {results.error && <ErrorNotice error={results.error} />}
      <Card p={0}>
        {results.isLoading ? <Loading /> : results.data?.items.length === 0 ? (
          <EmptyState title="No products found" description={inStock ? "Try a different spelling, or turn off “In stock only”." : "Try a generic name, e.g. “amoxicillin”."} />
        ) : (
          <Table.ScrollContainer minWidth={960}>
            <Table stickyHeader>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Product</Table.Th>
                  <Table.Th>Form / pack</Table.Th>
                  <Table.Th>Supplier</Table.Th>
                  <Table.Th ta="right">Unit price</Table.Th>
                  <Table.Th>Availability</Table.Th>
                  <Table.Th>Earliest expiry</Table.Th>
                  <Table.Th w={210}>Quantity</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {results.data?.items.map((p) => <ProductRow key={p.id} product={p} onInfo={() => setDetail(p.id)} />)}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Card>
      {pages > 1 && (
        <Group justify="space-between" mt="md">
          <Text size="sm" c="dimmed">{results.data?.total} products</Text>
          <Pagination value={page} onChange={setPage} total={pages} />
        </Group>
      )}
      <ProductDrawer id={detail} onClose={() => setDetail(null)} />
    </>
  );
}

function ProductRow({ product: p, onInfo }: { product: Product; onInfo: () => void }) {
  const add = useCart((s) => s.add);
  const inCart = useCart((s) => s.lines[p.id]?.quantity ?? 0);
  const [qty, setQty] = useState<number | string>(1);
  const max = Math.max(0, p.stock_available - inCart);
  const addToCart = () => {
    const n = Number(qty);
    if (!n || n < 1) return;
    if (n > max) {
      notifications.show({ color: "orange", message: `Only ${max} more available from ${p.supplier_name}.` });
      return;
    }
    add(p, n);
    setQty(1);
    notifications.show({ color: "teal", message: `Added ${n} × ${p.name}`, autoClose: 2000 });
  };

  return (
    <Table.Tr>
      <Table.Td>
        <Group gap={6} wrap="nowrap">
          <div>
            <Text fw={600} size="sm">{p.name} {p.strength}</Text>
            <Text size="xs" c="dimmed">{p.generic_name}{p.manufacturer && ` · ${p.manufacturer}`}</Text>
          </div>
          <ActionIcon variant="subtle" size="sm" onClick={onInfo} aria-label="Product details"><IconInfoCircle size={16} /></ActionIcon>
        </Group>
        {SCHEDULE_BADGE[p.schedule] && <Badge size="xs" color={SCHEDULE_BADGE[p.schedule].color} variant="light" mt={4}>{SCHEDULE_BADGE[p.schedule].label}</Badge>}
      </Table.Td>
      <Table.Td><Text size="sm">{DOSAGE_FORMS[p.dosage_form]}</Text><Text size="xs" c="dimmed">{p.pack_size}</Text></Table.Td>
      <Table.Td><Text size="sm">{p.supplier_name}</Text></Table.Td>
      <Table.Td ta="right"><Text fw={600} size="sm">{money(p.unit_price, p.currency)}</Text></Table.Td>
      <Table.Td><StockBadge qty={p.stock_available} /></Table.Td>
      <Table.Td><ExpiryBadge expiry={p.nearest_expiry} /></Table.Td>
      <Table.Td>
        <Group gap={6} wrap="nowrap">
          <NumberInput w={90} min={1} max={max || undefined} value={qty} onChange={setQty} disabled={!max} aria-label={`Quantity of ${p.name}`}
            onKeyDown={(e) => e.key === "Enter" && addToCart()} />
          <Button onClick={addToCart} disabled={!max} leftSection={<IconShoppingCartPlus size={16} />} px="sm">Add</Button>
        </Group>
        {inCart > 0 && <Text size="xs" c="teal" mt={2}>{inCart} in cart</Text>}
      </Table.Td>
    </Table.Tr>
  );
}

function ProductDrawer({ id, onClose }: { id: number | null; onClose: () => void }) {
  const product = useQuery({ queryKey: ["product", id], queryFn: () => catalogApi.product(id!), enabled: id !== null });
  const p = product.data;
  return (
    <Drawer opened={id !== null} onClose={onClose} position="right" size="md" title="Product details">
      {product.isLoading && <Loading />}
      {p && (
        <Stack>
          <div>
            <Title order={4}>{p.name} {p.strength}</Title>
            <Text c="dimmed">{p.generic_name}</Text>
          </div>
          <Table variant="vertical" withTableBorder>
            <Table.Tbody>
              <Table.Tr><Table.Th w={150}>Supplier</Table.Th><Table.Td>{p.supplier_name}</Table.Td></Table.Tr>
              <Table.Tr><Table.Th>Manufacturer</Table.Th><Table.Td>{p.manufacturer ?? "—"}</Table.Td></Table.Tr>
              <Table.Tr><Table.Th>Dosage form</Table.Th><Table.Td>{DOSAGE_FORMS[p.dosage_form]}</Table.Td></Table.Tr>
              <Table.Tr><Table.Th>Pack size</Table.Th><Table.Td>{p.pack_size ?? "—"}</Table.Td></Table.Tr>
              <Table.Tr><Table.Th>MCAZ category</Table.Th><Table.Td>{SCHEDULES[p.schedule] ?? p.schedule}</Table.Td></Table.Tr>
              <Table.Tr><Table.Th>MCAZ reg. no.</Table.Th><Table.Td>{p.mcaz_registration_number ?? <Text span c="orange" size="sm">Not provided by supplier</Text>}</Table.Td></Table.Tr>
              <Table.Tr><Table.Th>Unit price</Table.Th><Table.Td>{money(p.unit_price, p.currency)}</Table.Td></Table.Tr>
            </Table.Tbody>
          </Table>
          {p.description && <Text size="sm">{p.description}</Text>}
          <Title order={5}>Batches available</Title>
          <Text size="xs" c="dimmed">Orders are filled from the earliest-expiring batch first.</Text>
          <Table withTableBorder>
            <Table.Thead><Table.Tr><Table.Th>Batch</Table.Th><Table.Th>Expiry</Table.Th><Table.Th ta="right">Qty</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {p.batches.map((b) => (
                <Table.Tr key={b.batch_number}><Table.Td>{b.batch_number}</Table.Td><Table.Td><ExpiryBadge expiry={b.expiry_date} /></Table.Td><Table.Td ta="right">{b.quantity_available}</Table.Td></Table.Tr>
              ))}
              {p.batches.length === 0 && <Table.Tr><Table.Td colSpan={3}><Text size="sm" c="dimmed">No stock right now. Added {date(p.created_at)}.</Text></Table.Td></Table.Tr>}
            </Table.Tbody>
          </Table>
        </Stack>
      )}
    </Drawer>
  );
}

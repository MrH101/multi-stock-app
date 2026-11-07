import { Alert, Badge, Button, FileInput, Group, Modal, ScrollArea, SegmentedControl, SimpleGrid, Stack, Table, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconDownload, IconFileSpreadsheet, IconUpload } from "@tabler/icons-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorNotice } from "@/shared/ui";
import { catalogApi, type ImportReport } from "./api";

const ACTION = {
  create: { label: "New", color: "teal" },
  update: { label: "Update", color: "blue" },
  unchanged: { label: "No change", color: "gray" },
  error: { label: "Error", color: "red" },
} as const;

/** Upload a CSV / Excel price list: preview every row, then apply. */
export function ImportPriceList({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [show, setShow] = useState<"problems" | "all">("problems");
  const preview = useMutation({ mutationFn: (f: File) => catalogApi.importPriceList(f, false), onSuccess: setReport });
  const apply = useMutation({
    mutationFn: (f: File) => catalogApi.importPriceList(f, true),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["my-products"] });
      notifications.show({ color: "teal", title: "Price list imported", message: `${r.summary.create} new, ${r.summary.update} updated, ${r.summary.batches_added} batches received${r.summary.error ? `, ${r.summary.error} rows skipped` : ""}.` });
      reset();
      onClose();
    },
  });
  const reset = () => {
    setFile(null);
    setReport(null);
    preview.reset();
    apply.reset();
  };
  const pick = (f: File | null) => {
    setFile(f);
    setReport(null);
    if (f) preview.mutate(f);
  };
  const s = report?.summary;
  const rows = (report?.rows ?? []).filter((r) => show === "all" || r.action === "error" || r.batch === "exists");
  const changes = s ? s.create + s.update + s.batches_added : 0;

  return (
    <Modal opened={opened} onClose={() => { reset(); onClose(); }} title="Import price list" size="xl">
      <Stack>
        <Text size="sm" c="dimmed">
          Upload your usual price list as CSV or Excel. Products are matched on your <b>SKU / item code</b>, so next week you can
          upload the new list and only prices that changed are updated. Optional batch, expiry and quantity columns load opening stock.
        </Text>
        <Group align="flex-end">
          <FileInput style={{ flex: 1 }} label="Price list file" placeholder="Choose .csv or .xlsx" accept=".csv,.xlsx,.xlsm,text/csv"
            leftSection={<IconFileSpreadsheet size={18} />} value={file} onChange={pick} clearable />
          <Button variant="subtle" leftSection={<IconDownload size={16} />} onClick={() => catalogApi.importTemplate()}>Template</Button>
        </Group>
        {preview.isPending && <Text size="sm">Checking your file…</Text>}
        {preview.error && <ErrorNotice error={preview.error} title="Can't read this file" />}
        {apply.error && <ErrorNotice error={apply.error} title="Import failed" />}
        {s && report && (
          <>
            <SimpleGrid cols={{ base: 2, sm: 5 }}>
              {(["create", "update", "unchanged", "error"] as const).map((k) => (
                <Stack key={k} gap={0} align="center" p="xs" style={{ border: "1px solid var(--mantine-color-gray-3)", borderRadius: 8 }}>
                  <Text fw={700} size="xl" c={ACTION[k].color}>{s[k]}</Text>
                  <Text size="xs" c="dimmed">{ACTION[k].label}</Text>
                </Stack>
              ))}
              <Stack gap={0} align="center" p="xs" style={{ border: "1px solid var(--mantine-color-gray-3)", borderRadius: 8 }}>
                <Text fw={700} size="xl" c="violet">{s.batches_added}</Text>
                <Text size="xs" c="dimmed">Batches to receive</Text>
              </Stack>
            </SimpleGrid>
            <Text size="xs" c="dimmed">
              Columns used: {Object.entries(report.columns).map(([h, f]) => `${h} → ${f.replace(/_/g, " ")}`).join(" · ")}
              {report.ignored_columns.length > 0 && <> · Ignored: {report.ignored_columns.join(", ")}</>}
            </Text>
            {s.error > 0 && <Alert color="orange" variant="light">{s.error} row{s.error > 1 ? "s have" : " has"} problems and will be skipped. Fix them in your sheet and upload again any time.</Alert>}
            <Group justify="space-between">
              <SegmentedControl size="xs" value={show} onChange={(v) => setShow(v as "problems" | "all")} data={[{ value: "problems", label: "Problems" }, { value: "all", label: `All rows (${s.total})` }]} />
            </Group>
            <ScrollArea.Autosize mah={320}>
              <Table striped>
                <Table.Thead><Table.Tr><Table.Th>Row</Table.Th><Table.Th>SKU</Table.Th><Table.Th>Product</Table.Th><Table.Th>Result</Table.Th><Table.Th>Details</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {rows.slice(0, 300).map((r) => (
                    <Table.Tr key={r.row}>
                      <Table.Td>{r.row}</Table.Td>
                      <Table.Td><Text size="sm" ff="monospace">{r.sku ?? "—"}</Text></Table.Td>
                      <Table.Td><Text size="sm">{r.name ?? "—"}</Text></Table.Td>
                      <Table.Td><Badge size="sm" variant="light" color={ACTION[r.action].color}>{ACTION[r.action].label}</Badge>{r.batch === "added" && <Badge size="sm" variant="light" color="violet" ml={4}>+ stock</Badge>}</Table.Td>
                      <Table.Td><Text size="xs" c={r.action === "error" ? "red" : "dimmed"}>{r.messages.join("; ")}</Text></Table.Td>
                    </Table.Tr>
                  ))}
                  {rows.length === 0 && <Table.Tr><Table.Td colSpan={5}><Text size="sm" c="dimmed">No problems found.</Text></Table.Td></Table.Tr>}
                </Table.Tbody>
              </Table>
            </ScrollArea.Autosize>
          </>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={() => { reset(); onClose(); }}>Cancel</Button>
          <Button leftSection={<IconUpload size={16} />} disabled={!file || !s || changes === 0} loading={apply.isPending} onClick={() => file && apply.mutate(file)}>
            {s ? `Import ${s.create + s.update} product${s.create + s.update === 1 ? "" : "s"}` : "Import"}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

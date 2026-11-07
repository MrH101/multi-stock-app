import { Alert, Badge, Button, Card, CopyButton, FileInput, Group, Modal, SegmentedControl, Stack, Text, Textarea, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconCheck, IconCopy, IconDeviceMobile, IconExternalLink, IconFileText, IconUpload } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAccount } from "@/shared/auth/session";
import { dateTime, money } from "@/shared/format";
import { ErrorNotice } from "@/shared/ui";
import { METHOD_LABEL, PAY_STATUS, paymentsApi, type Method, type Payment, type PaymentOptions } from "./api";

const MOBILE: Method[] = ["ecocash", "onemoney", "innbucks"];

/** Pay an order (pharmacy) or see and confirm its payments (supplier). */
export function PaymentPanel({ orderNumber, orderStatus }: { orderNumber: string; orderStatus: string }) {
  const { isPharmacy, isSupplier, canManage } = useAccount();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const options = useQuery({ queryKey: ["payments", orderNumber, "options"], queryFn: () => paymentsApi.options(orderNumber) });
  const payments = useQuery({
    queryKey: ["payments", orderNumber],
    queryFn: () => paymentsApi.list(orderNumber),
    // while a mobile prompt is open, check every few seconds
    refetchInterval: (q) => (q.state.data?.some((p) => p.status === "PENDING") ? 5000 : false),
  });
  const pending = payments.data?.find((p) => p.status === "PENDING");
  const refresh = () => ["payments", "orders"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));

  // a pending Paynow payment is checked against Paynow on each poll, and on return from Paynow's page
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(() => paymentsApi.refresh(pending.id).then((p) => p.status !== "PENDING" && refresh()).catch(() => {}), 5000);
    return () => clearInterval(t);
  }, [pending?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const ref = params.get("payment");
    const p = payments.data?.find((x) => x.reference === ref);
    if (p) {
      paymentsApi.refresh(p.id).finally(refresh);
      params.delete("payment");
      setParams(params, { replace: true });
    }
  }, [payments.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const o = options.data;
  const paid = payments.data?.find((p) => p.status === "PAID");
  const awaiting = payments.data?.filter((p) => p.status === "AWAITING_CONFIRMATION") ?? [];

  return (
    <Card mb="lg" className="no-print">
      <Group justify="space-between" mb="sm">
        <Text fw={600}>Payment</Text>
        {paid ? <Badge color="green">Paid · {METHOD_LABEL[paid.method]}</Badge> : o?.payment_status && o.payment_status !== "UNPAID" ? <Badge variant="light">{o.payment_status.replace("_", " ").toLowerCase()}</Badge> : <Badge variant="light" color="gray">Unpaid</Badge>}
      </Group>
      {options.error && <ErrorNotice error={options.error} />}
      {o && <Text size="xl" fw={700} mb="sm">{money(o.amount, o.currency)}</Text>}

      {pending && <PendingPayment p={pending} />}
      {isPharmacy && o && !paid && !pending && orderStatus !== "REJECTED" && orderStatus !== "CANCELLED" && (
        o.methods.length ? <PayForm orderNumber={orderNumber} methods={o.methods} bank={o.bank} onDone={refresh} hasAwaiting={awaiting.length > 0} /> : <Text size="sm" c="dimmed">{o.reason}</Text>
      )}
      {!isPharmacy && o?.reason && !paid && <Text size="sm" c="dimmed">{o.reason}</Text>}

      {awaiting.map((p) => <ProofReview key={p.id} p={p} canReview={isSupplier && canManage} onDone={refresh} />)}
      {(payments.data?.length ?? 0) > 0 && (
        <Stack gap={4} mt="md">
          <Text size="xs" fw={600} c="dimmed">History</Text>
          {payments.data!.map((p) => (
            <Group key={p.id} justify="space-between" wrap="nowrap">
              <Text size="xs">{dateTime(p.created_at)} · {METHOD_LABEL[p.method]}{p.provider_reference ? ` · ${p.provider_reference}` : ""}</Text>
              <Badge size="xs" variant="light" color={PAY_STATUS[p.status].color}>{PAY_STATUS[p.status].label}</Badge>
            </Group>
          ))}
          {payments.data!.filter((p) => p.error || p.note).slice(0, 1).map((p) => <Text key={p.id} size="xs" c="dimmed">{p.error ?? p.note}</Text>)}
        </Stack>
      )}
    </Card>
  );
}

function PendingPayment({ p }: { p: Payment }) {
  return (
    <Alert color="blue" icon={<IconDeviceMobile size={18} />} title={p.method === "paynow_web" ? "Finish paying on Paynow" : "Approve the payment on your phone"} mb="sm">
      <Stack gap={6}>
        {p.instructions && <Text size="sm">{p.instructions}</Text>}
        {p.phone && <Text size="sm">A prompt was sent to {p.phone}. Enter your PIN to approve {money(p.amount, p.currency)}.</Text>}
        {p.innbucks_code && (
          <Group gap="xs">
            <Text size="sm">InnBucks code: <b>{p.innbucks_code}</b></Text>
            <CopyButton value={p.innbucks_code}>{({ copied, copy }) => <Button size="compact-xs" variant="subtle" onClick={copy} leftSection={copied ? <IconCheck size={12} /> : <IconCopy size={12} />}>{copied ? "Copied" : "Copy"}</Button>}</CopyButton>
          </Group>
        )}
        {p.redirect_url && <Button component="a" href={p.redirect_url} size="xs" leftSection={<IconExternalLink size={14} />}>Open Paynow to pay</Button>}
        <Text size="xs" c="dimmed">This page updates by itself once the payment goes through.</Text>
      </Stack>
    </Alert>
  );
}

function PayForm({ orderNumber, methods, bank, onDone, hasAwaiting }: {
  orderNumber: string; methods: Method[]; bank: PaymentOptions["bank"]; onDone: () => void; hasAwaiting: boolean;
}) {
  const { user, organization } = useAccount();
  const [method, setMethod] = useState<Method>(methods.includes("ecocash") ? "ecocash" : methods[0]);
  const [phone, setPhone] = useState(user?.phone ?? organization?.phone ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [ref, setRef] = useState("");
  const start = useMutation({
    mutationFn: () => paymentsApi.start(orderNumber, method, MOBILE.includes(method) ? phone : undefined),
    onSuccess: (p) => {
      onDone();
      if (p.redirect_url) window.location.href = p.redirect_url;
    },
  });
  const upload = useMutation({
    mutationFn: () => paymentsApi.uploadProof(orderNumber, file!, ref || undefined),
    onSuccess: () => {
      notifications.show({ color: "teal", message: "Proof of payment sent. The supplier will confirm it." });
      setFile(null);
      setRef("");
      onDone();
    },
  });

  return (
    <Stack gap="sm">
      <SegmentedControl fullWidth size="xs" value={method} onChange={(v) => setMethod(v as Method)} data={methods.map((m) => ({ value: m, label: METHOD_LABEL[m] }))} />
      {MOBILE.includes(method) && (
        <>
          <TextInput label={`${METHOD_LABEL[method]} number`} placeholder="0771 234 567" value={phone} onChange={(e) => setPhone(e.currentTarget.value)} inputMode="tel" />
          <Button leftSection={<IconDeviceMobile size={16} />} loading={start.isPending} disabled={!phone.trim()} onClick={() => start.mutate()}>Send payment prompt</Button>
        </>
      )}
      {method === "paynow_web" && <Button leftSection={<IconExternalLink size={16} />} loading={start.isPending} onClick={() => start.mutate()}>Pay on Paynow</Button>}
      {method === "bank_transfer" && bank && (
        <>
          <Card withBorder p="sm" bg="var(--mantine-color-gray-0)">
            <Text size="sm"><b>{bank.bank_name}</b>{bank.bank_branch ? `, ${bank.bank_branch}` : ""}</Text>
            <Text size="sm">{bank.bank_account_name}</Text>
            <Group gap={4}><Text size="sm" ff="monospace">{bank.bank_account_number}</Text>
              <CopyButton value={bank.bank_account_number ?? ""}>{({ copied, copy }) => <Button size="compact-xs" variant="subtle" onClick={copy}>{copied ? "Copied" : "Copy"}</Button>}</CopyButton></Group>
            <Text size="xs" c="dimmed">Use reference <b>{orderNumber}</b>.{bank.payment_instructions ? ` ${bank.payment_instructions}` : ""}</Text>
          </Card>
          <FileInput label="Proof of payment" placeholder="PDF, JPG or PNG" accept="application/pdf,image/png,image/jpeg" value={file} onChange={setFile} leftSection={<IconFileText size={16} />} />
          <TextInput label="Bank reference (optional)" value={ref} onChange={(e) => setRef(e.currentTarget.value)} />
          <Button leftSection={<IconUpload size={16} />} disabled={!file} loading={upload.isPending} onClick={() => upload.mutate()}>{hasAwaiting ? "Add another proof" : "Send proof of payment"}</Button>
        </>
      )}
      {(start.error || upload.error) && <ErrorNotice error={start.error ?? upload.error} title="Payment not started" />}
    </Stack>
  );
}

function ProofReview({ p, canReview, onDone }: { p: Payment; canReview: boolean; onDone: () => void }) {
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");
  const review = useMutation({
    mutationFn: (accept: boolean) => paymentsApi.review(p.id, accept, note || undefined),
    onSuccess: () => { setRejecting(false); onDone(); },
  });
  return (
    <Alert color="yellow" title="Bank transfer, waiting for the supplier to confirm" mt="sm">
      <Stack gap={6}>
        {p.proofs.map((f) => (
          <Group key={f.id} gap="xs">
            <Button size="compact-xs" variant="subtle" leftSection={<IconFileText size={14} />} onClick={() => paymentsApi.openProof(p.id, f.id)}>{f.filename}</Button>
            <Text size="xs" c="dimmed">{f.bank_reference ? `ref ${f.bank_reference} · ` : ""}{f.uploaded_by}, {dateTime(f.created_at)}</Text>
          </Group>
        ))}
        {canReview && (
          <Group gap="xs">
            <Button size="xs" color="green" loading={review.isPending && review.variables} onClick={() => review.mutate(true)}>Money received</Button>
            <Button size="xs" variant="light" color="red" onClick={() => setRejecting(true)}>Not received</Button>
          </Group>
        )}
        {review.error && <ErrorNotice error={review.error} />}
      </Stack>
      <Modal opened={rejecting} onClose={() => setRejecting(false)} title="Reject proof of payment">
        <Stack>
          <Textarea label="Reason (shown to the pharmacy)" autosize minRows={2} value={note} onChange={(e) => setNote(e.currentTarget.value)} placeholder="e.g. No transfer with this reference has reached our account" />
          <Group justify="flex-end"><Button variant="default" onClick={() => setRejecting(false)}>Back</Button><Button color="red" disabled={!note.trim()} loading={review.isPending} onClick={() => review.mutate(false)}>Reject</Button></Group>
        </Stack>
      </Modal>
    </Alert>
  );
}

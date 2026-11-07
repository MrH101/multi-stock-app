import { Anchor, Button, Grid, PasswordInput, SegmentedControl, Stack, Text, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "@/shared/auth/session";
import { ErrorNotice } from "@/shared/ui";
import { identityApi, type RegisterInput } from "./api";
import { AuthLayout } from "./AuthLayout";

export default function RegisterPage() {
  const navigate = useNavigate();
  const setSession = useSession((s) => s.setSession);
  const form = useForm<RegisterInput & { confirm: string }>({
    initialValues: { org_type: "PHARMACY", org_name: "", license_number: "", org_phone: "", address: "", city: "", full_name: "", email: "", password: "", confirm: "" },
    validate: {
      org_name: (v) => (v.trim().length >= 2 ? null : "Required"),
      license_number: (v) => (v.trim().length >= 3 ? null : "Enter your MCAZ licence number"),
      full_name: (v) => (v.trim().length >= 2 ? null : "Required"),
      email: (v) => (/^\S+@\S+\.\S+$/.test(v) ? null : "Enter a valid email"),
      password: (v) => (v.length >= 8 ? null : "At least 8 characters"),
      confirm: (v, all) => (v === all.password ? null : "Passwords do not match"),
    },
  });
  const register = useMutation({
    mutationFn: ({ confirm: _c, ...body }: typeof form.values) => identityApi.register(body),
    onSuccess: (session) => {
      setSession(session);
      navigate("/", { replace: true });
    },
  });
  const isPharmacy = form.values.org_type === "PHARMACY";

  return (
    <AuthLayout title="Create your account" subtitle="It takes about two minutes. You'll be the account owner and can add staff later." width={620}>
      <form onSubmit={form.onSubmit((v) => register.mutate(v))}>
        <Stack>
          {register.error && <ErrorNotice error={register.error} title="Registration failed" />}
          <div>
            <Text size="sm" fw={500} mb={6}>I am registering a…</Text>
            <SegmentedControl
              fullWidth
              size="md"
              data={[
                { value: "PHARMACY", label: "Pharmacy (I buy medicines)" },
                { value: "SUPPLIER", label: "Supplier / wholesaler (I sell)" },
              ]}
              {...form.getInputProps("org_type")}
            />
          </div>
          <Grid>
            <Grid.Col span={{ base: 12, sm: 7 }}>
              <TextInput label={isPharmacy ? "Pharmacy name" : "Company name"} required {...form.getInputProps("org_name")} />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 5 }}>
              <TextInput label="MCAZ licence number" required {...form.getInputProps("license_number")} />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 7 }}>
              <TextInput label="Address" {...form.getInputProps("address")} />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 5 }}>
              <TextInput label="City / town" {...form.getInputProps("city")} />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6 }}>
              <TextInput label="Your full name" required {...form.getInputProps("full_name")} />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6 }}>
              <TextInput label="Phone / WhatsApp" {...form.getInputProps("org_phone")} />
            </Grid.Col>
            <Grid.Col span={12}>
              <TextInput label="Work email (used to sign in)" type="email" required {...form.getInputProps("email")} />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6 }}>
              <PasswordInput label="Password" required description="At least 8 characters" {...form.getInputProps("password")} />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6 }}>
              <PasswordInput label="Confirm password" required {...form.getInputProps("confirm")} />
            </Grid.Col>
          </Grid>
          <Button type="submit" size="md" loading={register.isPending}>
            Create account
          </Button>
          <Text size="sm" ta="center">
            Already registered? <Anchor component={Link} to="/login">Sign in</Anchor>
          </Text>
        </Stack>
      </form>
    </AuthLayout>
  );
}

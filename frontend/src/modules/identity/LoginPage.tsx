import { Anchor, Button, PasswordInput, Stack, Text, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useMutation } from "@tanstack/react-query";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useSession } from "@/shared/auth/session";
import { ErrorNotice } from "@/shared/ui";
import { identityApi } from "./api";
import { AuthLayout } from "./AuthLayout";

export default function LoginPage() {
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/";
  const { accessToken, setSession } = useSession();
  const form = useForm({
    initialValues: { email: "", password: "" },
    validate: { email: (v) => (/^\S+@\S+\.\S+$/.test(v) ? null : "Enter a valid email"), password: (v) => (v ? null : "Enter your password") },
  });
  const login = useMutation({
    mutationFn: (v: typeof form.values) => identityApi.login(v.email, v.password),
    onSuccess: (session) => {
      setSession(session);
      navigate(from, { replace: true });
    },
  });
  if (accessToken) return <Navigate to="/" replace />;

  return (
    <AuthLayout title="Sign in" subtitle="Order medicines and manage stock in one place.">
      <form onSubmit={form.onSubmit((v) => login.mutate(v))}>
        <Stack>
          {login.error && <ErrorNotice error={login.error} title="Sign in failed" />}
          <TextInput label="Email" type="email" autoComplete="email" autoFocus size="md" {...form.getInputProps("email")} />
          <PasswordInput label="Password" autoComplete="current-password" size="md" {...form.getInputProps("password")} />
          <Button type="submit" size="md" loading={login.isPending} fullWidth>
            Sign in
          </Button>
          <Text size="sm" ta="center">
            New to Multi-Stock?{" "}
            <Anchor component={Link} to="/register">
              Register your pharmacy or company
            </Anchor>
          </Text>
        </Stack>
      </form>
    </AuthLayout>
  );
}

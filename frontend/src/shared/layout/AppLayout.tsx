import { AppShell, Avatar, Badge, Burger, Button, Group, Menu, NavLink, Text, ThemeIcon, UnstyledButton } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconBuildingStore, IconChevronDown, IconClipboardList, IconLayoutDashboard, IconLogout, IconMessages,
  IconActivity, IconPackage, IconPlus, IconSearch, IconSparkles, IconSettings, IconShieldCheck, IconShoppingCart, IconSpeakerphone, IconUsers,
} from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { insightsApi } from "@/modules/insights/api";
import { messagingApi } from "@/modules/messaging/api";
import { NotificationBell } from "@/modules/messaging/NotificationBell";
import { cartCount, useCart } from "@/modules/orders/cart";
import { useAccount, useSession } from "@/shared/auth/session";
import { useRealtime } from "@/shared/realtime";

interface NavItem {
  to: string;
  label: string;
  icon: typeof IconSearch;
  badge?: number;
}

export function AppLayout() {
  useRealtime();
  const [opened, { toggle, close }] = useDisclosure();
  const { user, organization, isPharmacy, isSupplier, isAdmin } = useAccount();
  const location = useLocation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const lines = useCart((s) => s.lines);
  const unread = useQuery({ queryKey: ["unread"], queryFn: messagingApi.unread, refetchInterval: 60_000, enabled: !isAdmin });
  const msgs = unread.data?.messages ?? 0;
  const alertCounts = useQuery({ queryKey: ["insights", "counts"], queryFn: insightsApi.counts, refetchInterval: 120_000 });
  const urgent = (alertCounts.data?.critical ?? 0) + (alertCounts.data?.warning ?? 0);
  const insights: NavItem = { to: "/insights", label: "Insights", icon: IconSparkles, badge: urgent };

  const nav: NavItem[] = isPharmacy
    ? [
        { to: "/", label: "Dashboard", icon: IconLayoutDashboard },
        insights,
        { to: "/catalog", label: "Order medicines", icon: IconSearch },
        { to: "/orders", label: "My orders", icon: IconClipboardList },
        { to: "/suppliers", label: "Suppliers", icon: IconBuildingStore },
        { to: "/messages", label: "Messages", icon: IconMessages, badge: msgs },
        { to: "/announcements", label: "Announcements", icon: IconSpeakerphone },
      ]
    : isSupplier
      ? [
          { to: "/", label: "Dashboard", icon: IconLayoutDashboard },
          insights,
          { to: "/orders", label: "Incoming orders", icon: IconClipboardList },
          { to: "/inventory", label: "Products & stock", icon: IconPackage },
          { to: "/pharmacies", label: "Pharmacies", icon: IconBuildingStore },
          { to: "/messages", label: "Messages", icon: IconMessages, badge: msgs },
          { to: "/announcements", label: "Announcements", icon: IconSpeakerphone },
        ]
      : [
          { to: "/", label: "Organisations", icon: IconShieldCheck },
          { to: "/monitoring", label: "Monitoring", icon: IconActivity, badge: urgent },
          { to: "/insights", label: "Ask the assistant", icon: IconSparkles },
          { to: "/orders", label: "All orders", icon: IconClipboardList },
          { to: "/announcements", label: "Announcements", icon: IconSpeakerphone },
        ];
  nav.push({ to: "/team", label: "Team", icon: IconUsers }, { to: "/settings", label: "Settings", icon: IconSettings });

  const active = (to: string) => (to === "/" ? location.pathname === "/" : location.pathname.startsWith(to));

  const signOut = () => {
    useSession.getState().clear();
    qc.clear();
    navigate("/login");
  };

  return (
    <AppShell header={{ height: 60 }} navbar={{ width: 240, breakpoint: "sm", collapsed: { mobile: !opened } }} padding="lg">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Toggle navigation" />
            <ThemeIcon size={32} radius="md" color="teal">
              <IconPlus size={20} stroke={3} />
            </ThemeIcon>
            <div>
              <Text fw={700} lh={1.1}>Multi-Stock</Text>
              <Text size="xs" c="dimmed" lh={1.1} visibleFrom="xs">
                {organization?.name}
              </Text>
            </div>
            {organization && !organization.verified && !isAdmin && (
              <Badge color="yellow" variant="light" visibleFrom="md">Verification pending</Badge>
            )}
          </Group>
          <Group gap="xs" wrap="nowrap">
            {isPharmacy && (
              <Button component={Link} to="/cart" variant={cartCount(lines) ? "filled" : "light"} leftSection={<IconShoppingCart size={18} />}>
                Cart{cartCount(lines) ? ` · ${cartCount(lines)}` : ""}
              </Button>
            )}
            <NotificationBell />
            <Menu position="bottom-end" width={220}>
              <Menu.Target>
                <UnstyledButton aria-label="Account menu">
                  <Group gap={6} wrap="nowrap">
                    <Avatar size={32} radius="xl" color="teal">
                      {user?.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("")}
                    </Avatar>
                    <IconChevronDown size={14} />
                  </Group>
                </UnstyledButton>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Label>
                  {user?.full_name} · {user?.role.toLowerCase()}
                </Menu.Label>
                <Menu.Item leftSection={<IconSettings size={16} />} component={Link} to="/settings">
                  Settings
                </Menu.Item>
                <Menu.Item leftSection={<IconLogout size={16} />} color="red" onClick={signOut}>
                  Sign out
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="sm">
        {nav.map((item) => (
          <NavLink
            key={item.to}
            component={Link}
            to={item.to}
            label={item.label}
            active={active(item.to)}
            onClick={close}
            leftSection={<item.icon size={20} stroke={1.6} />}
            rightSection={item.badge ? <Badge size="sm" circle color="red">{item.badge}</Badge> : null}
            styles={{ root: { borderRadius: 8, marginBottom: 2 }, label: { fontSize: 15 } }}
          />
        ))}
      </AppShell.Navbar>
      <AppShell.Main bg="var(--mantine-color-gray-0)">
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}

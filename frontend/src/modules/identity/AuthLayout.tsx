import { Center, Group, Paper, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconPlus } from "@tabler/icons-react";
import type { ReactNode } from "react";

export function AuthLayout({ title, subtitle, children, width = 420 }: { title: string; subtitle: string; children: ReactNode; width?: number }) {
  return (
    <Center mih="100vh" bg="var(--mantine-color-gray-0)" p="md">
      <Stack w="100%" maw={width} gap="lg">
        <Group gap="sm" justify="center">
          <ThemeIcon size={40} radius="md" color="teal">
            <IconPlus size={26} stroke={3} />
          </ThemeIcon>
          <Title order={2}>Multi-Stock</Title>
        </Group>
        <Paper p="xl" radius="md" shadow="sm">
          <Title order={3}>{title}</Title>
          <Text c="dimmed" size="sm" mb="lg">
            {subtitle}
          </Text>
          {children}
        </Paper>
      </Stack>
    </Center>
  );
}

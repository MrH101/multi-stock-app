import { createTheme } from "@mantine/core";

export const theme = createTheme({
  primaryColor: "teal",
  defaultRadius: "md",
  fontFamily: "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
  headings: { fontWeight: "700" },
  components: {
    Button: { defaultProps: { size: "sm" } },
    Table: { defaultProps: { verticalSpacing: "sm", highlightOnHover: true } },
    Card: { defaultProps: { withBorder: true, radius: "md", padding: "lg" } },
    Paper: { defaultProps: { withBorder: true } },
  },
});

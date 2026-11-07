import { notifications } from "@mantine/notifications";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useSession } from "@/shared/auth/session";

/** Live updates from the notifications service; refreshes affected data and shows a toast. */
export function useRealtime() {
  const token = useSession((s) => s.accessToken);
  const qc = useQueryClient();

  useEffect(() => {
    if (!token) return;
    let ws: WebSocket | null = null;
    let ping: ReturnType<typeof setInterval>;
    let retry: ReturnType<typeof setTimeout>;
    let attempt = 0;
    let closed = false;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/api/notifications/ws?token=${encodeURIComponent(token)}`);
      ws.onopen = () => {
        attempt = 0;
        ping = setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send("ping"), 25_000);
      };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data) as { kind: string; title?: string; body?: string; link?: string };
        qc.invalidateQueries({ queryKey: ["unread"] });
        if (msg.kind === "notification") {
          qc.invalidateQueries({ queryKey: ["notifications"] });
          qc.invalidateQueries({ queryKey: ["insights"] });
          if (msg.link?.startsWith("/orders")) {
            qc.invalidateQueries({ queryKey: ["orders"] });
            qc.invalidateQueries({ queryKey: ["summary"] });
          }
          if (!msg.link?.startsWith("/messages")) notifications.show({ title: msg.title, message: msg.body, autoClose: 6000 });
        }
        if (msg.kind === "message") qc.invalidateQueries({ queryKey: ["conversations"] });
      };
      ws.onclose = () => {
        clearInterval(ping);
        if (!closed) retry = setTimeout(connect, Math.min(30_000, 1000 * 2 ** attempt++));
      };
    };
    connect();
    return () => {
      closed = true;
      clearInterval(ping);
      clearTimeout(retry);
      ws?.close();
    };
  }, [token, qc]);
}

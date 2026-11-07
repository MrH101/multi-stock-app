import { api } from "@/shared/api/http";

export interface Notification {
  id: number;
  kind: string;
  title: string;
  body: string;
  link: string | null;
  created_at: string;
  read: boolean;
}

export interface Conversation {
  id: number;
  pharmacy_org_id: number;
  pharmacy_name: string;
  supplier_org_id: number;
  supplier_name: string;
  subject: string;
  order_number: string | null;
  last_message_at: string | null;
  last_message_preview: string;
  unread: number;
  counterpart_name: string;
}

export interface Message {
  id: number;
  conversation_id: number;
  sender_org_id: number;
  sender_name: string;
  body: string;
  created_at: string;
}

export interface Broadcast {
  id: number;
  sender_org_name: string;
  sender_org_type: string;
  audience: "ALL" | "PHARMACIES" | "SUPPLIERS";
  title: string;
  body: string;
  created_at: string;
}

export const messagingApi = {
  notifications: () => api<Notification[]>("notifications", "/notifications"),
  unread: () => api<{ notifications: number; messages: number }>("notifications", "/unread"),
  markRead: (id: number) => api<void>("notifications", `/notifications/${id}/read`, { method: "POST" }),
  markAllRead: () => api<void>("notifications", "/notifications/read-all", { method: "POST" }),
  conversations: () => api<Conversation[]>("notifications", "/conversations"),
  startConversation: (body: { counterpart_org_id: number; counterpart_org_name: string; subject: string; body: string; order_number?: string }) =>
    api<Conversation>("notifications", "/conversations", { method: "POST", body }),
  messages: (id: number) => api<Message[]>("notifications", `/conversations/${id}/messages`),
  send: (id: number, body: string) => api<Message>("notifications", `/conversations/${id}/messages`, { method: "POST", body: { body } }),
  broadcasts: () => api<Broadcast[]>("notifications", "/broadcasts"),
  createBroadcast: (body: { title: string; body: string; audience: Broadcast["audience"] }) =>
    api<Broadcast>("notifications", "/broadcasts", { method: "POST", body }),
};

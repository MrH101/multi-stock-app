import { api } from "@/shared/api/http";
import type { Organization, OrgType, Role, SessionPayload, User } from "@/shared/auth/session";

export interface RegisterInput {
  org_type: Exclude<OrgType, "PLATFORM">;
  org_name: string;
  license_number: string;
  org_phone?: string;
  address?: string;
  city?: string;
  full_name: string;
  email: string;
  password: string;
}

export const identityApi = {
  login: (email: string, password: string) =>
    api<SessionPayload>("identity", "/auth/login", { method: "POST", body: { email, password }, auth: false }),
  register: (body: RegisterInput) => api<SessionPayload>("identity", "/auth/register", { method: "POST", body, auth: false }),
  changePassword: (current_password: string, new_password: string) =>
    api<void>("identity", "/me/password", { method: "POST", body: { current_password, new_password } }),
  myOrg: () => api<Organization>("identity", "/organizations/me"),
  updateMyOrg: (body: Partial<Organization>) => api<Organization>("identity", "/organizations/me", { method: "PATCH", body }),
  organizations: (query: { type?: OrgType; q?: string }) => api<Organization[]>("identity", "/organizations", { query: { ...query } }),
  adminUpdateOrg: (id: number, body: { verified?: boolean; is_active?: boolean }) =>
    api<Organization>("identity", `/admin/organizations/${id}`, { method: "PATCH", body }),
  team: () => api<User[]>("identity", "/users"),
  addMember: (body: { email: string; full_name: string; phone?: string; role: Role; password: string }) =>
    api<User>("identity", "/users", { method: "POST", body }),
  updateMember: (id: number, body: { role?: Role; is_active?: boolean; full_name?: string }) =>
    api<User>("identity", `/users/${id}`, { method: "PATCH", body }),
};

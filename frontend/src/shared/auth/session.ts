import { create } from "zustand";
import { persist } from "zustand/middleware";

export type OrgType = "PHARMACY" | "SUPPLIER" | "PLATFORM";
export type Role = "OWNER" | "MANAGER" | "STAFF";

export interface User {
  id: number;
  org_id: number;
  email: string;
  full_name: string;
  phone: string | null;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface Organization {
  id: number;
  name: string;
  type: OrgType;
  license_number: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  city: string | null;
  verified: boolean;
  is_active: boolean;
  created_at: string;
}

export interface SessionPayload {
  access_token: string;
  refresh_token: string;
  user: User;
  organization: Organization;
}

interface SessionState {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  organization: Organization | null;
  setSession: (s: SessionPayload) => void;
  setOrganization: (o: Organization) => void;
  clear: () => void;
}

export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      organization: null,
      setSession: (s) => set({ accessToken: s.access_token, refreshToken: s.refresh_token, user: s.user, organization: s.organization }),
      setOrganization: (organization) => set({ organization }),
      clear: () => set({ accessToken: null, refreshToken: null, user: null, organization: null }),
    }),
    { name: "multistock-session" },
  ),
);

/** Convenience hook for role/org-based UI decisions. */
export function useAccount() {
  const { user, organization } = useSession();
  return {
    user,
    organization,
    isPharmacy: organization?.type === "PHARMACY",
    isSupplier: organization?.type === "SUPPLIER",
    isAdmin: organization?.type === "PLATFORM",
    isOwner: user?.role === "OWNER",
    canManage: user?.role === "OWNER" || user?.role === "MANAGER",
  };
}

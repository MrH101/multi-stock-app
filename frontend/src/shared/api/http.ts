import { useSession, type SessionPayload } from "@/shared/auth/session";

export type Service = "identity" | "catalog" | "orders" | "notifications" | "agent";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public problems: string[] = [],
  ) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | undefined | null | (string | number)[]>;

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  /** Multipart upload; sent as-is (the browser sets the boundary). */
  form?: FormData;
  query?: Query;
  auth?: boolean;
}

function buildUrl(service: Service, path: string, query?: Query) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => params.append(key, String(v)));
    else params.set(key, String(value));
  }
  const qs = params.toString();
  return `/api/${service}${path}${qs ? `?${qs}` : ""}`;
}

/** Turns FastAPI error bodies into one human sentence (+ optional detail list). */
async function toError(res: Response): Promise<ApiError> {
  let detail: unknown;
  try {
    detail = (await res.json()).detail;
  } catch {
    /* non-JSON body */
  }
  if (typeof detail === "string") return new ApiError(detail, res.status);
  if (Array.isArray(detail)) {
    const problems = detail.map((d: { loc?: string[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(" › ")}: ${d.msg}`);
    return new ApiError("Please check the highlighted information", res.status, problems);
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    const d = detail as { message: string; problems?: string[] };
    return new ApiError(d.message, res.status, d.problems ?? []);
  }
  if (res.status >= 500) return new ApiError("Something went wrong on our side. Please try again in a moment.", res.status);
  return new ApiError(`Request failed (${res.status})`, res.status);
}

let refreshing: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  const { refreshToken, setSession, clear } = useSession.getState();
  if (!refreshToken) return false;
  refreshing ??= fetch(buildUrl("identity", "/auth/refresh"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
    .then(async (res) => {
      if (!res.ok) {
        clear();
        return false;
      }
      setSession((await res.json()) as SessionPayload);
      return true;
    })
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

export async function api<T>(service: Service, path: string, opts: RequestOptions = {}): Promise<T> {
  const send = () => {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (opts.body !== undefined && !opts.form) headers["Content-Type"] = "application/json";
    const token = useSession.getState().accessToken;
    if (opts.auth !== false && token) headers.Authorization = `Bearer ${token}`;
    return fetch(buildUrl(service, path, opts.query), {
      method: opts.method ?? "GET",
      headers,
      body: opts.form ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
    });
  };

  let res: Response;
  try {
    res = await send();
    if (res.status === 401 && opts.auth !== false && (await refreshSession())) res = await send();
  } catch {
    throw new ApiError("Cannot reach the server. Check your internet connection.", 0);
  }
  if (res.status === 401 && opts.auth !== false) useSession.getState().clear();
  if (!res.ok) throw await toError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Downloads a protected file (e.g. a CSV template) with the user's session. */
export async function download(service: Service, path: string, filename: string) {
  const token = useSession.getState().accessToken;
  const res = await fetch(buildUrl(service, path), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw await toError(res);
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

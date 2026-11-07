import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAccount, useSession } from "@/shared/auth/session";
import { AppLayout } from "@/shared/layout/AppLayout";
import { Loading } from "@/shared/ui";

// Each domain module is code-split so it loads independently, mirroring the backend services.
const LoginPage = lazy(() => import("@/modules/identity/LoginPage"));
const RegisterPage = lazy(() => import("@/modules/identity/RegisterPage"));
const TeamPage = lazy(() => import("@/modules/identity/TeamPage"));
const SettingsPage = lazy(() => import("@/modules/identity/SettingsPage"));
const DirectoryPage = lazy(() => import("@/modules/identity/DirectoryPage"));
const AdminOrganizationsPage = lazy(() => import("@/modules/identity/AdminOrganizationsPage"));
const CatalogPage = lazy(() => import("@/modules/catalog/CatalogPage"));
const InventoryPage = lazy(() => import("@/modules/catalog/InventoryPage"));
const ProductStockPage = lazy(() => import("@/modules/catalog/ProductStockPage"));
const CartPage = lazy(() => import("@/modules/orders/CartPage"));
const OrdersPage = lazy(() => import("@/modules/orders/OrdersPage"));
const OrderDetailPage = lazy(() => import("@/modules/orders/OrderDetailPage"));
const MessagesPage = lazy(() => import("@/modules/messaging/MessagesPage"));
const AnnouncementsPage = lazy(() => import("@/modules/messaging/AnnouncementsPage"));
const PharmacyDashboard = lazy(() => import("@/modules/dashboard/PharmacyDashboard"));
const SupplierDashboard = lazy(() => import("@/modules/dashboard/SupplierDashboard"));

function RequireAuth({ children }: { children: ReactNode }) {
  const token = useSession((s) => s.accessToken);
  const location = useLocation();
  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

function Only({ when, children }: { when: boolean; children: ReactNode }) {
  return when ? <>{children}</> : <Navigate to="/" replace />;
}

export function App() {
  const { isPharmacy, isSupplier, isAdmin } = useAccount();
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route element={<RequireAuth><AppLayout /></RequireAuth>}>
          <Route index element={isPharmacy ? <PharmacyDashboard /> : isSupplier ? <SupplierDashboard /> : <AdminOrganizationsPage />} />
          <Route path="catalog" element={<Only when={isPharmacy}><CatalogPage /></Only>} />
          <Route path="cart" element={<Only when={isPharmacy}><CartPage /></Only>} />
          <Route path="suppliers" element={<Only when={isPharmacy}><DirectoryPage type="SUPPLIER" /></Only>} />
          <Route path="pharmacies" element={<Only when={isSupplier}><DirectoryPage type="PHARMACY" /></Only>} />
          <Route path="inventory" element={<Only when={isSupplier}><InventoryPage /></Only>} />
          <Route path="inventory/:productId" element={<Only when={isSupplier}><ProductStockPage /></Only>} />
          <Route path="orders" element={<OrdersPage />} />
          <Route path="orders/:orderId" element={<OrderDetailPage />} />
          <Route path="messages" element={<Only when={!isAdmin}><MessagesPage /></Only>} />
          <Route path="messages/:conversationId" element={<Only when={!isAdmin}><MessagesPage /></Only>} />
          <Route path="announcements" element={<AnnouncementsPage />} />
          <Route path="team" element={<TeamPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}

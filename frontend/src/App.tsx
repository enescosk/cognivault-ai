import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { Dashboard } from "./components/Dashboard";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { LoginRoute } from "./components/LoginRoute";
import { RequireRole } from "./components/RequireRole";
import { RoleRedirect } from "./components/RoleRedirect";
import { ToastContainer } from "./components/ui/Toast";
import { AuthProvider } from "./context/AuthContext";
import { I18nProvider } from "./i18n";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginRoute />} />

      {/* Bireysel müşteri paneli — /customer/* */}
      <Route
        path="/customer/*"
        element={
          <RequireRole roles={["customer"]}>
            <ErrorBoundary scope="Customer workspace">
              <Dashboard audience="customer" />
            </ErrorBoundary>
          </RequireRole>
        }
      />

      {/* Operator / admin (kurumsal) paneli — /operator/* */}
      <Route
        path="/operator/*"
        element={
          <RequireRole roles={["operator", "admin"]}>
            <ErrorBoundary scope="Operator workspace">
              <Dashboard audience="operator" />
            </ErrorBoundary>
          </RequireRole>
        }
      />

      {/* Admin alias — şu an operator paneliyle aynı, gelecekte ayrılabilir. */}
      <Route path="/admin/*" element={<Navigate to="/operator" replace />} />

      <Route path="/" element={<RoleRedirect />} />
      <Route path="*" element={<RoleRedirect />} />
    </Routes>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <I18nProvider>
          <AuthProvider>
            <AppRoutes />
            <ToastContainer />
          </AuthProvider>
        </I18nProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

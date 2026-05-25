import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { LoginScreen } from "./LoginScreen";
import { canonicalHomeFor } from "./RequireRole";

/** /login route wrapper. Redirects authenticated users away from the login screen. */
export function LoginRoute() {
  const { user, loading, login, register } = useAuth();
  const location = useLocation();

  if (loading) return <div className="loading-shell">Preparing secure workspace…</div>;
  if (user) {
    const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;
    return <Navigate to={from && from !== "/login" ? from : canonicalHomeFor(user.role.name)} replace />;
  }
  return <LoginScreen onLogin={login} onRegister={register} />;
}

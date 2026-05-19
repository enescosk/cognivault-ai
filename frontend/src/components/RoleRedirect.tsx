import { Navigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { canonicalHomeFor } from "./RequireRole";

/** Routes the root URL to the audience-specific home (or /login if unauthenticated). */
export function RoleRedirect() {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading-shell">Preparing secure workspace…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={canonicalHomeFor(user.role.name)} replace />;
}

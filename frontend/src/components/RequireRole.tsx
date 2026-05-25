import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import type { RoleName } from "../types/api";

interface Props {
  /** Roles permitted to render the children. Empty/undefined = any authenticated user. */
  roles?: RoleName[];
  children: React.ReactNode;
}

/**
 * Route-level guard. Redirects unauthenticated users to /login and authenticated
 * users with the wrong role to their canonical home (so an admin who hits a
 * /customer/* URL ends up on /operator, not on a 404).
 *
 * Backend RBAC is still authoritative; this is a UX-level enforcement that
 * keeps the address bar honest about which audience a page belongs to.
 */
export function RequireRole({ roles, children }: Props) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <div className="loading-shell">Preparing secure workspace…</div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;

  if (!roles || roles.length === 0) {
    return <>{children}</>;
  }

  if (!roles.includes(user.role.name as RoleName)) {
    const home = canonicalHomeFor(user.role.name as RoleName);
    return <Navigate to={home} replace />;
  }

  return <>{children}</>;
}

export function canonicalHomeFor(role: RoleName | string): string {
  if (role === "customer") return "/customer";
  if (role === "operator" || role === "admin") return "/operator";
  return "/";
}

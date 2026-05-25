import type { ReactNode } from "react";

import { useAuth } from "../context/AuthContext";
import type { RoleName } from "../types/api";

interface Props {
  allowed: RoleName | RoleName[];
  children: ReactNode;
  fallback?: ReactNode;
}

/**
 * Renders `children` only when the current user has one of the allowed roles.
 * If not authenticated or the role does not match, renders `fallback` (default: nothing).
 *
 * This is a lightweight guard for role-conditional UI inside the dashboard.
 * It is NOT a substitute for backend RBAC, which still enforces every API call.
 */
export function ProtectedRoute({ allowed, children, fallback = null }: Props) {
  const { user } = useAuth();
  if (!user) return <>{fallback}</>;
  const allowedList = Array.isArray(allowed) ? allowed : [allowed];
  if (!allowedList.includes(user.role.name as RoleName)) {
    return <>{fallback}</>;
  }
  return <>{children}</>;
}

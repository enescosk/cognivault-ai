export const dashboardKeys = {
  all: ["dashboard"] as const,
  sessions: (token: string | null) => [...dashboardKeys.all, "sessions", token] as const,
  session: (token: string | null, id: number | null) => [...dashboardKeys.all, "session", id, token] as const,
  appointments: (token: string | null) => [...dashboardKeys.all, "appointments", token] as const,
  metrics: (token: string | null) => [...dashboardKeys.all, "metrics", token] as const,
  auditLogs: (token: string | null) => [...dashboardKeys.all, "audit-logs", token] as const,
  users: (token: string | null) => [...dashboardKeys.all, "users", token] as const,
};

export const clinicalKeys = {
  all: ["clinical"] as const,
  overview: (token: string) => [...clinicalKeys.all, "overview", token] as const,
  compliance: (token: string) => [...clinicalKeys.all, "compliance", token] as const,
  patent: (token: string) => [...clinicalKeys.all, "patent", token] as const,
  slots: (token: string) => [...clinicalKeys.all, "slots", token] as const,
  appointments: (token: string) => [...clinicalKeys.all, "appointments", token] as const,
  conversation: (token: string, id: number | null) => [...clinicalKeys.all, "conversation", id, token] as const,
};

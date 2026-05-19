import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { listAgentDecisions } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useT } from "../i18n";
import { SkeletonBlock } from "./ui/Skeleton";

type FilterMode = "all" | "needs_human" | "auto";

export function DecisionLogView() {
  const { token } = useAuth();
  const { t } = useT();
  const [filter, setFilter] = useState<FilterMode>("all");

  const requires_human =
    filter === "needs_human" ? true : filter === "auto" ? false : undefined;

  const { data, error, isLoading, isFetching } = useQuery({
    queryKey: ["agent-decisions", { filter, hasToken: Boolean(token) }],
    queryFn: () => listAgentDecisions(token!, { limit: 50, requires_human }),
    enabled: Boolean(token),
    refetchInterval: 30_000,
  });

  const rows = data ?? null;

  return (
    <div className="decision-mini">
      <div className="decision-mini-header">
        <div className="decision-mini-title">
          {t("nav.decisions")}
          {isFetching && rows ? <span className="decision-meta"> · {t("common.loading")}</span> : null}
        </div>
        <div className="locale-switcher" role="tablist">
          <button
            type="button"
            className={filter === "all" ? "active" : ""}
            onClick={() => setFilter("all")}
          >
            {t("decisions.filter.all")}
          </button>
          <button
            type="button"
            className={filter === "needs_human" ? "active" : ""}
            onClick={() => setFilter("needs_human")}
          >
            {t("decisions.filter.needs_human")}
          </button>
          <button
            type="button"
            className={filter === "auto" ? "active" : ""}
            onClick={() => setFilter("auto")}
          >
            {t("decisions.filter.auto")}
          </button>
        </div>
      </div>

      {error ? (
        <div className="error-box">
          {error instanceof Error ? error.message : t("common.error_generic")}
        </div>
      ) : null}
      {isLoading ? <SkeletonBlock count={4} /> : null}
      {rows !== null && rows.length === 0 ? (
        <div className="decision-meta">{t("common.empty")}</div>
      ) : null}
      {rows?.map((row) => {
        const pillCls = `decision-pill decision-pill-${row.risk}`;
        return (
          <div key={row.id} className="decision-row">
            <div className="decision-row-head">
              <div>
                <strong style={{ fontSize: "0.9rem" }}>{row.intent}</strong>
                <span className="decision-meta"> · {row.agent_type}</span>
              </div>
              <span className={pillCls}>
                {row.risk === "low" || row.risk === "medium" || row.risk === "high"
                  ? t(`decisions.risk.${row.risk}` as const)
                  : row.risk}
              </span>
            </div>
            <div className="decision-meta">
              {row.action ?? "—"} · {Math.round((row.confidence ?? 0) * 100)}% · {" "}
              {new Date(row.created_at).toLocaleString()}
            </div>
            {row.reason ? <div className="decision-meta">{row.reason}</div> : null}
          </div>
        );
      })}
    </div>
  );
}

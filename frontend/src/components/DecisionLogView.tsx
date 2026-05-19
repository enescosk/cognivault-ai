import { useEffect, useState } from "react";

import { listAgentDecisions, type AgentDecisionLog } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useT } from "../i18n";
import { SkeletonBlock } from "./ui/Skeleton";

const RISK_LABEL: Record<string, string> = {
  low: "Düşük",
  medium: "Orta",
  high: "Yüksek",
};

export function DecisionLogView() {
  const { token } = useAuth();
  const { t } = useT();
  const [rows, setRows] = useState<AgentDecisionLog[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "needs_human" | "auto">("all");

  useEffect(() => {
    if (!token) return;
    setError(null);
    setRows(null);
    const requires_human =
      filter === "needs_human" ? true : filter === "auto" ? false : undefined;
    listAgentDecisions(token, { limit: 50, requires_human })
      .then(setRows)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed"));
  }, [token, filter]);

  return (
    <div className="decision-mini">
      <div className="decision-mini-header">
        <div className="decision-mini-title">{t("nav.decisions")}</div>
        <div className="locale-switcher" role="tablist">
          <button
            type="button"
            className={filter === "all" ? "active" : ""}
            onClick={() => setFilter("all")}
          >
            Tümü
          </button>
          <button
            type="button"
            className={filter === "needs_human" ? "active" : ""}
            onClick={() => setFilter("needs_human")}
          >
            İnsan onayı
          </button>
          <button
            type="button"
            className={filter === "auto" ? "active" : ""}
            onClick={() => setFilter("auto")}
          >
            Otomatik
          </button>
        </div>
      </div>

      {error ? <div className="error-box">{error}</div> : null}
      {rows === null && !error ? <SkeletonBlock count={4} /> : null}
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
              <span className={pillCls}>{RISK_LABEL[row.risk] ?? row.risk}</span>
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

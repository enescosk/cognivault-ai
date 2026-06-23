import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { listAgentDecisions, type AgentDecisionLog } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useT } from "../i18n";
import { Badge, StatusDot } from "./ui";
import { SkeletonBlock } from "./ui/Skeleton";

type FilterMode = "all" | "needs_human" | "auto";
type Tone = "green" | "amber" | "red" | "neutral";

const RISK_TONE: Record<string, Tone> = { low: "green", medium: "amber", high: "red" };

function timeShort(iso: string): string {
  return new Date(iso).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
}

/**
 * Karar / Denetim Günlüğü — her AI kararının (routing/triyaj) izini gösterir.
 * "Her AI aksiyonu audit trail'e düşer" iddiasının görünür kanıtı: risk, güven,
 * insan-yükseltme ve request_id (denetim izi kimliği). Gerçek veri: GET /agents/decisions.
 */
export function DecisionLogView() {
  const { token } = useAuth();
  const { t } = useT();
  const [filter, setFilter] = useState<FilterMode>("all");

  const requires_human = filter === "needs_human" ? true : filter === "auto" ? false : undefined;

  const { data, error, isLoading, isFetching } = useQuery({
    queryKey: ["agent-decisions", { filter, hasToken: Boolean(token) }],
    queryFn: () => listAgentDecisions(token!, { limit: 50, requires_human }),
    enabled: Boolean(token),
    refetchInterval: 30_000,
  });

  const rows = data ?? null;

  return (
    <div className="declog">
      <div className="declog-head">
        <div className="declog-title">
          {t("nav.decisions")}
          {isFetching && rows ? <span className="declog-live">{t("common.loading")}</span> : null}
        </div>
        <div className="declog-filters" role="tablist">
          <button type="button" className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>
            {t("decisions.filter.all")}
          </button>
          <button type="button" className={filter === "needs_human" ? "active" : ""} onClick={() => setFilter("needs_human")}>
            {t("decisions.filter.needs_human")}
          </button>
          <button type="button" className={filter === "auto" ? "active" : ""} onClick={() => setFilter("auto")}>
            {t("decisions.filter.auto")}
          </button>
        </div>
      </div>

      {error ? (
        <div className="declog-error">{error instanceof Error ? error.message : t("common.error_generic")}</div>
      ) : null}
      {isLoading ? <SkeletonBlock count={4} /> : null}
      {rows !== null && rows.length === 0 ? <div className="declog-empty">{t("common.empty")}</div> : null}

      <div className="declog-list">
        {rows?.map((row) => {
          const tone = RISK_TONE[row.risk] ?? "neutral";
          const conf = Math.round((row.confidence ?? 0) * 100);
          const riskLabel =
            row.risk === "low" || row.risk === "medium" || row.risk === "high"
              ? t(`decisions.risk.${row.risk}` as const)
              : row.risk;
          return (
            <article key={row.id} className="declog-row">
              <div className="declog-row-top">
                <span className="declog-agent">
                  {row.intent.replace(/_/g, " ")}
                  <small> · {row.agent_type}</small>
                </span>
                <Badge tone={tone}>{riskLabel}</Badge>
              </div>
              <div className="declog-meta">
                {row.requires_human ? (
                  <StatusDot tone="red">insana</StatusDot>
                ) : (
                  <StatusDot tone="green">otomatik</StatusDot>
                )}
                <span className="declog-sep">·</span>
                <span>%{conf}</span>
                {row.action ? (
                  <>
                    <span className="declog-sep">·</span>
                    <span>{row.action.replace(/_/g, " ")}</span>
                  </>
                ) : null}
                <span className="declog-sep">·</span>
                <span>{timeShort(row.created_at)}</span>
              </div>
              {row.reason ? <div className="declog-reason">{row.reason.replace(/_/g, " ")}</div> : null}
              <div className="declog-audit" title="Denetim izi kaydı">
                iz · #{row.id}
                {row.request_id ? ` · ${row.request_id.slice(0, 8)}` : ""}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

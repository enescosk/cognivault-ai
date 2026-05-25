import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getUsageSummary } from "../api/client";

type Props = {
  token: string;
};

const RANGES = [
  { days: 1, label: "Bugün" },
  { days: 7, label: "7 gün" },
  { days: 30, label: "30 gün" },
];

const usdFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

const tokenFormatter = new Intl.NumberFormat("tr-TR");

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return tokenFormatter.format(n);
}

export function UsageCostCard({ token }: Props) {
  const [days, setDays] = useState(7);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["usage-summary", days],
    queryFn: () => getUsageSummary(token, days),
    refetchInterval: 60_000,   // her dakika tazele
    staleTime: 30_000,
  });

  return (
    <div className="usage-card">
      <div className="usage-card-header">
        <div>
          <div className="usage-card-title">LLM Kullanımı & Maliyet</div>
          <div className="usage-card-subtitle">
            {isLoading ? "Yükleniyor…" : `Son ${days} gün`}
          </div>
        </div>
        <div className="usage-range-pills">
          {RANGES.map((r) => (
            <button
              key={r.days}
              className={`usage-range-pill ${days === r.days ? "is-active" : ""}`}
              onClick={() => setDays(r.days)}
              type="button"
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {isError ? (
        <div className="usage-error">Veri alınamadı.</div>
      ) : (
        <>
          <div className="usage-headline">
            <div className="usage-headline-cell">
              <div className="usage-headline-label">Toplam Maliyet</div>
              <div className="usage-headline-value usage-cost">
                {usdFormatter.format(data?.total_cost_usd ?? 0)}
              </div>
            </div>
            <div className="usage-headline-cell">
              <div className="usage-headline-label">Token</div>
              <div className="usage-headline-value">
                {formatTokens(data?.total_tokens ?? 0)}
              </div>
            </div>
            <div className="usage-headline-cell">
              <div className="usage-headline-label">Çağrı</div>
              <div className="usage-headline-value">{data?.total_calls ?? 0}</div>
            </div>
          </div>

          {data && data.by_model.length > 0 && (
            <div className="usage-breakdown">
              <div className="usage-breakdown-title">Model bazlı</div>
              {data.by_model.map((m) => (
                <div className="usage-breakdown-row" key={m.model}>
                  <div className="usage-breakdown-name">
                    <span className={`usage-provider-dot usage-provider-${m.provider}`} />
                    {m.model}
                  </div>
                  <div className="usage-breakdown-meta">
                    <span>{m.calls} çağrı</span>
                    <span>{formatTokens(m.total_tokens)}</span>
                    <span className="usage-breakdown-cost">{usdFormatter.format(m.cost_usd)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {data && Object.keys(data.by_agent_type).length > 0 && (
            <div className="usage-breakdown">
              <div className="usage-breakdown-title">Ajan bazlı</div>
              {Object.entries(data.by_agent_type)
                .sort(([, a], [, b]) => b - a)
                .map(([agent, cost]) => (
                  <div className="usage-breakdown-row" key={agent}>
                    <div className="usage-breakdown-name">{agent}</div>
                    <div className="usage-breakdown-meta">
                      <span className="usage-breakdown-cost">{usdFormatter.format(cost)}</span>
                    </div>
                  </div>
                ))}
            </div>
          )}

          {data && data.total_calls === 0 && (
            <div className="usage-empty">Bu dönemde LLM çağrısı yok.</div>
          )}
        </>
      )}
    </div>
  );
}

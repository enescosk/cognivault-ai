import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { getUpcomingClinicalAppointments } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { ErrorBoundary } from "./ErrorBoundary";
import { SkeletonBlock } from "./ui/Skeleton";

/**
 * Klinik personeli için gerçek-zamanlı randevu listesi.
 * Route: /operator/appointments
 *
 * Yeni patient page'de randevu oluştuğunda backend `clinical_appointments`
 * tablosuna düşüyor + iki SMS log'una. Bu sayfa o tabloyu çekip
 * klinik ekibinin tek bakışta görebileceği halde gösteriyor.
 *
 * Window: varsayılan 7 gün, kullanıcı 1/3/7/30 günlük chip ile değiştirir.
 */

const WINDOW_OPTIONS: Array<{ label: string; minutes: number }> = [
  { label: "Bugün", minutes: 24 * 60 },
  { label: "3 Gün", minutes: 3 * 24 * 60 },
  { label: "7 Gün", minutes: 7 * 24 * 60 },
  { label: "30 Gün", minutes: 30 * 24 * 60 },
];

function formatStartsAt(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const dt = new Date(iso);
    return new Intl.DateTimeFormat("tr-TR", {
      weekday: "long",
      day: "2-digit",
      month: "long",
      hour: "2-digit",
      minute: "2-digit",
    }).format(dt);
  } catch {
    return iso;
  }
}

function statusBadge(status: string): { label: string; cls: string } {
  switch (status) {
    case "pending":
      return { label: "Bekliyor", cls: "appt-badge-pending" };
    case "confirmed":
      return { label: "Onaylandı", cls: "appt-badge-confirmed" };
    case "cancelled":
      return { label: "İptal", cls: "appt-badge-cancelled" };
    default:
      return { label: status, cls: "appt-badge-neutral" };
  }
}

export function ClinicAppointmentsPage() {
  const { token, user, logout } = useAuth();
  const navigate = useNavigate();
  const [windowMinutes, setWindowMinutes] = useState<number>(7 * 24 * 60);

  const query = useQuery({
    queryKey: ["clinical-appointments-upcoming", windowMinutes],
    queryFn: () => getUpcomingClinicalAppointments(token!, windowMinutes),
    enabled: Boolean(token),
    refetchInterval: 20_000, // her 20s'de bir tazele — yeni randevular hızlı görünsün
    staleTime: 10_000,
  });

  const rows = useMemo(() => query.data ?? [], [query.data]);
  const total = rows.length;
  const pendingCount = rows.filter((r) => r.status === "pending").length;

  if (!user) return null;

  return (
    <div className="appt-shell">
      <header className="appt-header">
        <div className="appt-header-left">
          <Link to="/operator" className="appt-back">← Panel</Link>
          <div>
            <h1>Klinik Randevuları</h1>
            <p>Hasta sayfasından + operatör panelinden oluşturulan tüm aktif randevular.</p>
          </div>
        </div>
        <div className="appt-header-right">
          <span className="appt-meta">
            {user.email}
            {query.isFetching ? " · yenileniyor…" : ""}
          </span>
          <button type="button" className="patient-cta-ghost" onClick={() => logout()}>
            Çıkış
          </button>
        </div>
      </header>

      <div className="appt-controls">
        <div className="appt-window-tabs" role="tablist">
          {WINDOW_OPTIONS.map((opt) => (
            <button
              key={opt.minutes}
              type="button"
              role="tab"
              aria-selected={windowMinutes === opt.minutes}
              className={`appt-tab ${windowMinutes === opt.minutes ? "is-active" : ""}`}
              onClick={() => setWindowMinutes(opt.minutes)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <div className="appt-summary">
          <span><strong>{total}</strong> randevu</span>
          <span className="appt-meta">·</span>
          <span><strong>{pendingCount}</strong> onay bekliyor</span>
        </div>
      </div>

      <ErrorBoundary scope="Clinic appointments">
        <div className="appt-list">
          {query.isLoading ? <SkeletonBlock count={5} /> : null}

          {query.error ? (
            <div className="patient-error-line">
              {(query.error as Error).message ?? "Randevu listesi yüklenemedi."}
            </div>
          ) : null}

          {!query.isLoading && rows.length === 0 ? (
            <div className="appt-empty">
              Bu pencerede randevu yok. Hasta sayfasından (`/c/&lt;slug&gt;`) yeni
              randevu oluşturulduğunda burada görünür.
            </div>
          ) : null}

          {rows.map((appt) => {
            const badge = statusBadge(appt.status);
            return (
              <article
                key={appt.id}
                className="appt-card"
                onClick={() => {
                  if (appt.conversation_id) {
                    navigate(`/operator/conversations/${appt.conversation_id}`);
                  }
                }}
              >
                <div className="appt-card-head">
                  <div className="appt-time">{formatStartsAt(appt.starts_at)}</div>
                  <span className={`appt-badge ${badge.cls}`}>{badge.label}</span>
                </div>
                <div className="appt-dept">{appt.department}</div>
                <div className="appt-meta-row">
                  <span>#{appt.id}</span>
                  {appt.conversation_id ? (
                    <span>· Sohbet #{appt.conversation_id}</span>
                  ) : null}
                  {appt.metadata_json?.source ? (
                    <span>· {String(appt.metadata_json.source)}</span>
                  ) : null}
                  {appt.metadata_json?.physician_name ? (
                    <span>· {String(appt.metadata_json.physician_name)}</span>
                  ) : null}
                </div>
                {appt.notes ? <div className="appt-notes">{appt.notes}</div> : null}
              </article>
            );
          })}
        </div>
      </ErrorBoundary>
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { listClinicalAppointments } from "../api/client";
import { useAuth } from "../context/AuthContext";
import type { ClinicalAppointmentRow } from "../types/api";
import { ErrorBoundary } from "./ErrorBoundary";
import { SkeletonBlock } from "./ui/Skeleton";

type StatusFilter = "active" | "pending" | "confirmed";

const WINDOW_OPTIONS: Array<{ label: string; days: number | null }> = [
  { label: "Tümü", days: null },
  { label: "Bugün", days: 1 },
  { label: "3 Gün", days: 3 },
  { label: "7 Gün", days: 7 },
  { label: "30 Gün", days: 30 },
];

const dayFormatter = new Intl.DateTimeFormat("tr-TR", { weekday: "long", day: "2-digit", month: "long" });
const timeFormatter = new Intl.DateTimeFormat("tr-TR", { hour: "2-digit", minute: "2-digit" });

function statusBadge(status: string): { label: string; cls: string } {
  if (status === "pending") return { label: "Onay bekliyor", cls: "appt-badge-pending" };
  if (status === "confirmed") return { label: "Onaylandı", cls: "appt-badge-confirmed" };
  if (status === "cancelled") return { label: "İptal", cls: "appt-badge-cancelled" };
  return { label: status, cls: "appt-badge-neutral" };
}

function dateKey(row: ClinicalAppointmentRow): string {
  if (!row.starts_at) return "unscheduled";
  const date = new Date(row.starts_at);
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

export function ClinicAppointmentsPage() {
  const { token, user, logout } = useAuth();
  const [windowDays, setWindowDays] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("active");

  const query = useQuery({
    queryKey: ["clinical-appointments-calendar"],
    queryFn: () => listClinicalAppointments(token!, 200),
    enabled: Boolean(token),
    refetchInterval: 20_000,
    staleTime: 10_000,
  });

  const rows = useMemo(() => {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const windowEnd = windowDays ? new Date(todayStart.getTime() + windowDays * 86_400_000) : null;
    return (query.data ?? [])
      .filter((row) => statusFilter === "active" ? row.status !== "cancelled" : row.status === statusFilter)
      .filter((row) => {
        if (!windowEnd || !row.starts_at) return true;
        const starts = new Date(row.starts_at);
        return starts >= todayStart && starts < windowEnd;
      })
      .sort((a, b) => {
        if (!a.starts_at) return 1;
        if (!b.starts_at) return -1;
        return new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime();
      });
  }, [query.data, statusFilter, windowDays]);

  const groups = useMemo(() => rows.reduce<Array<{ key: string; label: string; rows: ClinicalAppointmentRow[] }>>((result, row) => {
    const key = dateKey(row);
    const existing = result.find((group) => group.key === key);
    if (existing) existing.rows.push(row);
    else result.push({ key, label: row.starts_at ? dayFormatter.format(new Date(row.starts_at)) : "Tarihi belirlenmemiş", rows: [row] });
    return result;
  }, []), [rows]);

  const pendingCount = rows.filter((row) => row.status === "pending").length;
  const confirmedCount = rows.filter((row) => row.status === "confirmed").length;

  if (!user) return null;

  return (
    <div className="appt-shell">
      <header className="appt-header">
        <div className="appt-header-left">
          <Link to="/operator" className="appt-back">← Panel</Link>
          <div>
            <h1>Hekim Takvimleri</h1>
            <p>Saat, hekim, ziyaret nedeni ve klinik işlem planıyla canlı randevu ajandası.</p>
          </div>
        </div>
        <div className="appt-header-right">
          <span className="appt-meta">{user.email}{query.isFetching ? " · yenileniyor…" : ""}</span>
          <button type="button" className="patient-cta-ghost" onClick={() => logout()}>Çıkış</button>
        </div>
      </header>

      <div className="appt-controls appt-controls--calendar">
        <div className="appt-window-tabs" role="tablist" aria-label="Tarih aralığı">
          {WINDOW_OPTIONS.map((option) => (
            <button key={option.label} type="button" role="tab" aria-selected={windowDays === option.days} className={`appt-tab ${windowDays === option.days ? "is-active" : ""}`} onClick={() => setWindowDays(option.days)}>{option.label}</button>
          ))}
        </div>
        <div className="appt-window-tabs" role="tablist" aria-label="Randevu durumu">
          {([ ["active", "Aktif"], ["pending", "Bekleyen"], ["confirmed", "Onaylanan"] ] as const).map(([id, label]) => (
            <button key={id} type="button" role="tab" aria-selected={statusFilter === id} className={`appt-tab ${statusFilter === id ? "is-active" : ""}`} onClick={() => setStatusFilter(id)}>{label}</button>
          ))}
        </div>
        <div className="appt-summary"><span><strong>{rows.length}</strong> randevu</span><span className="appt-meta">·</span><span><strong>{pendingCount}</strong> bekleyen</span><span className="appt-meta">·</span><span><strong>{confirmedCount}</strong> onaylı</span></div>
      </div>

      <ErrorBoundary scope="Clinic appointments calendar">
        <div className="appt-calendar-list">
          {query.isLoading ? <SkeletonBlock count={5} /> : null}
          {query.error ? <div className="patient-error-line">{(query.error as Error).message ?? "Randevu listesi yüklenemedi."}</div> : null}
          {!query.isLoading && !groups.length ? <div className="appt-empty">Seçilen aralıkta randevu yok.</div> : null}
          {groups.map((group) => (
            <section key={group.key} className="appt-calendar-day">
              <div className="appt-calendar-day-head"><h2>{group.label}</h2><span>{group.rows.length} randevu</span></div>
              <div className="appt-calendar-timeline">
                {group.rows.map((appointment) => <CalendarAppointment key={appointment.id} appointment={appointment} />)}
              </div>
            </section>
          ))}
        </div>
      </ErrorBoundary>
    </div>
  );
}

function CalendarAppointment({ appointment }: { appointment: ClinicalAppointmentRow }) {
  const badge = statusBadge(appointment.status);
  const completed = appointment.procedures.filter((item) => item.status === "completed").length;
  return (
    <article className={`appt-calendar-card ${appointment.status}`}>
      <div className="appt-calendar-time">
        <strong>{appointment.starts_at ? timeFormatter.format(new Date(appointment.starts_at)) : "—:—"}</strong>
        <span>{appointment.ends_at ? timeFormatter.format(new Date(appointment.ends_at)) : `${appointment.duration_minutes} dk`}</span>
      </div>
      <div className="appt-calendar-rail" />
      <div className="appt-calendar-main">
        <div className="appt-card-head">
          <div>
            <strong>{appointment.patient_name ?? `Hasta #${appointment.patient_id}`}</strong>
            <span>{appointment.physician_name ?? "Hekim ataması bekliyor"} · {appointment.department}</span>
          </div>
          <span className={`appt-badge ${badge.cls}`}>{badge.label}</span>
        </div>
        <p className={appointment.visit_reason ? "" : "is-empty"}>{appointment.visit_reason ?? "Ziyaret nedeni henüz girilmedi."}</p>
        <div className="appt-calendar-procedures">
          <span>İşlem planı</span>
          {appointment.procedures.length ? (
            <ul>{appointment.procedures.map((procedure) => <li key={procedure.id} className={procedure.status}><i /><span><strong>{procedure.name}</strong><small>{[procedure.tooth ? `Diş ${procedure.tooth}` : null, procedure.code].filter(Boolean).join(" · ")}</small></span><em>{procedure.status === "completed" ? "Tamamlandı" : procedure.status === "in_progress" ? "İşlemde" : procedure.status === "cancelled" ? "İptal" : "Planlandı"}</em></li>)}</ul>
          ) : <small>Henüz işlem eklenmedi.</small>}
          {appointment.procedures.length ? <b>{completed}/{appointment.procedures.length} tamamlandı</b> : null}
        </div>
        <div className="appt-meta-row"><span>#{appointment.id}</span><span>· {appointment.duration_minutes} dakika</span>{appointment.branch_name ? <span>· {appointment.branch_name}</span> : null}{appointment.conversation_id ? <Link to={`/operator/conversations/${appointment.conversation_id}`}>Sohbeti aç →</Link> : null}</div>
      </div>
    </article>
  );
}

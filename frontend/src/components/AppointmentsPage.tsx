import { useState } from "react";
import type { Appointment } from "../types/api";

type Props = { appointments: Appointment[] };

type Filter = "all" | "confirmed" | "pending" | "cancelled";

const trDate = new Intl.DateTimeFormat("tr-TR", { dateStyle: "long" });
const trTime = new Intl.DateTimeFormat("tr-TR", { timeStyle: "short" });

const statusCfg: Record<string, { label: string; color: string; bg: string }> = {
  confirmed: { label: "Onaylı",   color: "#68d391", bg: "rgba(104,211,145,0.12)" },
  cancelled: { label: "İptal",    color: "#fc8181", bg: "rgba(252,129,129,0.12)" },
  pending:   { label: "Bekliyor", color: "#f6ad55", bg: "rgba(246,173,85,0.12)"  },
};

const filterLabels: { key: Filter; label: string }[] = [
  { key: "all",       label: "Tümü"    },
  { key: "confirmed", label: "Onaylı"  },
  { key: "pending",   label: "Bekliyor"},
  { key: "cancelled", label: "İptal"   },
];

function isUpcoming(s: string) {
  const d = new Date(s);
  return d.getTime() > Date.now();
}

export function AppointmentsPage({ appointments }: Props) {
  const [filter, setFilter] = useState<Filter>("all");

  const filtered = appointments.filter(a =>
    filter === "all" ? true : a.status === filter
  ).sort((a, b) => new Date(b.scheduled_at).getTime() - new Date(a.scheduled_at).getTime());

  const counts: Record<Filter, number> = {
    all:       appointments.length,
    confirmed: appointments.filter(a => a.status === "confirmed").length,
    pending:   appointments.filter(a => a.status === "pending").length,
    cancelled: appointments.filter(a => a.status === "cancelled").length,
  };

  return (
    <div className="apts-page">
      {/* Header */}
      <div className="apts-header">
        <div className="apts-header-left">
          <h2 className="apts-title">Randevularım</h2>
          <p className="apts-subtitle">Tüm randevu geçmişiniz ve aktif rezervasyonlarınız</p>
        </div>
        <div className="apts-stats">
          <div className="apts-stat">
            <span className="apts-stat-val" style={{ color: "#68d391" }}>{counts.confirmed}</span>
            <span className="apts-stat-label">Onaylı</span>
          </div>
          <div className="apts-stat-divider" />
          <div className="apts-stat">
            <span className="apts-stat-val" style={{ color: "#f6ad55" }}>{counts.pending}</span>
            <span className="apts-stat-label">Bekliyor</span>
          </div>
          <div className="apts-stat-divider" />
          <div className="apts-stat">
            <span className="apts-stat-val" style={{ color: "#fc8181" }}>{counts.cancelled}</span>
            <span className="apts-stat-label">İptal</span>
          </div>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="apts-filters">
        {filterLabels.map(({ key, label }) => (
          <button
            key={key}
            className={`apts-filter-btn ${filter === key ? "apts-filter-btn--active" : ""}`}
            onClick={() => setFilter(key)}
            type="button"
          >
            {label}
            {counts[key] > 0 && (
              <span className="apts-filter-count">{counts[key]}</span>
            )}
          </button>
        ))}
      </div>

      {/* Grid */}
      {filtered.length === 0 ? (
        <div className="apts-empty">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.18 }}>
            <rect x="3" y="4" width="18" height="18" rx="2"/>
            <line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/>
            <line x1="3" y1="10" x2="21" y2="10"/>
          </svg>
          <p>Bu filtrede randevu bulunamadı</p>
        </div>
      ) : (
        <div className="apts-grid">
          {filtered.map(apt => {
            const d = new Date(apt.scheduled_at);
            const st = statusCfg[apt.status] ?? statusCfg.pending;
            const upcoming = isUpcoming(apt.scheduled_at) && apt.status === "confirmed";
            return (
              <div key={apt.id} className={`apts-card ${upcoming ? "apts-card--upcoming" : ""}`}>
                {/* Üst şerit */}
                <div className="apts-card-top">
                  <span className="apts-card-dept">{apt.department}</span>
                  <span className="apts-card-status" style={{ color: st.color, background: st.bg }}>
                    {upcoming && <span className="active-apt-dot" style={{ width: 5, height: 5, marginRight: 5 }} />}
                    {st.label}
                  </span>
                </div>

                {/* Kod */}
                <div className="apts-card-code">{apt.confirmation_code}</div>

                {/* Tarih & Saat */}
                <div className="apts-card-datetime">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="4" width="18" height="18" rx="2"/>
                    <line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/>
                    <line x1="3" y1="10" x2="21" y2="10"/>
                  </svg>
                  <span>{trDate.format(d)}</span>
                  <span className="apts-card-time">{trTime.format(d)}</span>
                </div>

                {/* Detaylar */}
                <div className="apts-card-details">
                  {apt.location && (
                    <div className="apts-card-row">
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/>
                      </svg>
                      {apt.location}
                    </div>
                  )}
                  {apt.contact_phone && (
                    <div className="apts-card-row">
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 013.07 9.81a19.79 19.79 0 01-3.07-8.68A2 2 0 012 .18h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L6.09 7.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/>
                      </svg>
                      {apt.contact_phone}
                    </div>
                  )}
                </div>

                {/* Amaç */}
                {apt.purpose && (
                  <div className="apts-card-purpose">{apt.purpose}</div>
                )}

                {/* Notlar */}
                {apt.notes && (
                  <div className="apts-card-notes">{apt.notes}</div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

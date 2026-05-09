import { useState } from "react";

type NoteStatus = "completed" | "follow_up" | "pending";
type FilterKey = "all" | NoteStatus;

type AppointmentNote = {
  id: number;
  title: string;
  date: string;
  summary: string;
  doctor: string;
  department: string;
  status: NoteStatus;
  followUpDate?: string;
};

const MOCK_NOTES: AppointmentNote[] = [
  { id: 1, title: "Dis kontrolu sonrasi notlar", date: "2026-05-09T14:30:00", summary: "Dis temizligi yapildi. Caplak dis temizlenmesi ve florid uygulamasi gerceklestirildi. 6 ay sonra kontrol onerisi verildi. Gunluk dis ipi kullanimi tavsiye edildi.", doctor: "Dr. Elif Yilmaz", department: "Dis Hekimligi", status: "completed" },
  { id: 2, title: "Cilt muayenesi degerlendirmesi", date: "2026-05-07T10:00:00", summary: "Alerjik reaksiyon nedeniyle tedavi baslandi. Antihistaminik ve topikal krem recelendi. 2 hafta sonra kontrol randevusu planlanmali.", doctor: "Dr. Kemal Aydin", department: "Dermatoloji", status: "follow_up", followUpDate: "2026-05-21T10:00:00" },
  { id: 3, title: "Genel saglik kontrolu", date: "2026-05-05T09:00:00", summary: "Yillik genel saglik kontrolu tamamlandi. Kan tahlili, idrar tahlili ve EKG sonuclari normal sinirlar icerisinde. Kolesterol degerleri hafif yuksek — diyet onerisi yapildi.", doctor: "Dr. Fatma Celik", department: "Genel Pratisyen", status: "completed" },
  { id: 4, title: "Psikolojik degerlendirme seansı", date: "2026-05-02T15:00:00", summary: "Ilk gorusme seansi tamamlandi. Stres yonetimi ve uyku duzeni uzerine gorusulder. Haftalik seans planlamasi onerisi yapildi.", doctor: "Dr. Ahmet Demir", department: "Psikoloji", status: "follow_up", followUpDate: "2026-05-16T15:00:00" },
  { id: 5, title: "Acil dis agrisi muayenesi", date: "2026-04-28T11:00:00", summary: "20 numara dis dolgusunda kirilma tespit edildi. Gecici dolgu uygulamasi yapildi. Kalici dolgu icin randevu alinmali.", doctor: "Dr. Elif Yilmaz", department: "Dis Hekimligi", status: "pending" },
];

const trDate = new Intl.DateTimeFormat("tr-TR", { dateStyle: "long" });
const trTime = new Intl.DateTimeFormat("tr-TR", { timeStyle: "short" });

const statusConfig: Record<NoteStatus, { label: string; color: string; bg: string }> = {
  completed: { label: "Tamamlandi", color: "#68d391", bg: "rgba(104,211,145,0.12)" },
  follow_up: { label: "Takip Gerekli", color: "#f6ad55", bg: "rgba(246,173,85,0.12)" },
  pending:   { label: "Bekliyor", color: "#63b3ed", bg: "rgba(99,179,237,0.12)" },
};

const filterLabels: { key: FilterKey; label: string }[] = [
  { key: "all", label: "Tumü" },
  { key: "completed", label: "Tamamlandi" },
  { key: "follow_up", label: "Takip" },
  { key: "pending", label: "Bekliyor" },
];

export function AppointmentNotes() {
  const [filter, setFilter] = useState<FilterKey>("all");
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const filtered = MOCK_NOTES.filter(n => filter === "all" || n.status === filter)
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

  return (
    <div className="apt-notes">
      <div className="apt-notes-header">
        <div>
          <h2 className="apt-notes-title">Randevu Notlari</h2>
          <p className="apt-notes-subtitle">Doktor degerlendirmeleri ve tedavi notlariniz</p>
        </div>
      </div>

      <div className="apt-notes-filters">
        {filterLabels.map(({ key, label }) => (
          <button
            key={key}
            className={`apt-notes-filter-btn ${filter === key ? "apt-notes-filter-btn--active" : ""}`}
            onClick={() => setFilter(key)}
            type="button"
          >
            {label}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="apt-notes-empty">
          <p>Bu kategoride not bulunamadi</p>
        </div>
      ) : (
        <div className="apt-notes-list">
          {filtered.map(note => {
            const d = new Date(note.date);
            const st = statusConfig[note.status];
            const expanded = expandedId === note.id;
            return (
              <div
                key={note.id}
                className={`apt-notes-card ${expanded ? "apt-notes-card--expanded" : ""}`}
                onClick={() => setExpandedId(expanded ? null : note.id)}
              >
                <div className="apt-notes-card-top">
                  <div className="apt-notes-card-left">
                    <span className="apt-notes-card-dept">{note.department}</span>
                    <h4 className="apt-notes-card-title">{note.title}</h4>
                  </div>
                  <span className="apt-notes-card-status" style={{ color: st.color, background: st.bg }}>
                    {st.label}
                  </span>
                </div>

                <div className="apt-notes-card-meta">
                  <span>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
                    </svg>
                    {trDate.format(d)} — {trTime.format(d)}
                  </span>
                  <span>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/>
                    </svg>
                    {note.doctor}
                  </span>
                </div>

                <p className="apt-notes-card-summary">{note.summary}</p>

                {expanded && note.followUpDate && (
                  <div className="apt-notes-card-followup">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="4" width="18" height="18" rx="2"/>
                      <line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/>
                      <line x1="3" y1="10" x2="21" y2="10"/>
                    </svg>
                    Kontrol tarihi: {trDate.format(new Date(note.followUpDate))} — {trTime.format(new Date(note.followUpDate))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

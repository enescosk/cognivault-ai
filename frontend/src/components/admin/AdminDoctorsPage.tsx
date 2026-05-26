import { useEffect, useState } from "react";
import { getDoctors, createDoctor, updateDoctor, deleteDoctor, type Doctor } from "../../api/client";
import { showToast } from "../ui/Toast";

interface Props {
  token: string;
}

export function AdminDoctorsPage({ token }: Props) {
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  // Edit / Add Form State
  const [formMode, setFormMode] = useState<"list" | "add" | "edit">("list");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [fullName, setFullName] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [isActive, setIsActive] = useState(true);

  async function loadDoctors() {
    setLoading(true);
    try {
      const data = await getDoctors(token);
      setDoctors(data);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Hekim listesi alınamadı.", "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadDoctors();
  }, [token]);

  function startAdd() {
    setFormMode("add");
    setEditingId(null);
    setFullName("");
    setSpecialty("");
    setIsActive(true);
  }

  function startEdit(doc: Doctor) {
    setFormMode("edit");
    setEditingId(doc.id);
    setFullName(doc.full_name);
    setSpecialty(doc.specialty);
    setIsActive(doc.is_active);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!fullName.trim() || !specialty.trim()) {
      showToast("Lütfen tüm alanları doldurun.", "info");
      return;
    }

    setBusy(true);
    try {
      if (formMode === "add") {
        await createDoctor(token, { full_name: fullName.trim(), specialty: specialty.trim(), is_active: isActive });
        showToast("Hekim başarıyla eklendi.", "success");
      } else if (formMode === "edit" && editingId !== null) {
        await updateDoctor(token, editingId, { full_name: fullName.trim(), specialty: specialty.trim(), is_active: isActive });
        showToast("Hekim başarıyla güncellendi.", "success");
      }
      setFormMode("list");
      void loadDoctors();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Hekim kaydedilemedi.", "error");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(id: number) {
    if (!window.confirm("Bu hekimi silmek istediğinizden emin misiniz?")) return;
    setBusy(true);
    try {
      await deleteDoctor(token, id);
      showToast("Hekim başarıyla silindi.", "success");
      void loadDoctors();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Hekim silinemedi.", "error");
    } finally {
      setBusy(false);
    }
  }

  if (loading && doctors.length === 0) {
    return <div className="clinical-empty">Hekim bilgileri yükleniyor...</div>;
  }

  return (
    <div className="clinic-card admin-doctors-card">
      <div className="clinical-card-top">
        <div>
          <span>Klinik Hekimleri</span>
          <h3>Klinik Bünyesindeki Hekimlerin Yönetimi</h3>
        </div>
        {formMode === "list" && (
          <button type="button" onClick={startAdd} className="patient-cta" style={{ background: "#1f6f68", color: "white", border: "0", padding: "8px 16px", borderRadius: "8px", fontWeight: "bold" }}>
            + Yeni Hekim Ekle
          </button>
        )}
      </div>

      {formMode === "list" ? (
        <div style={{ overflowX: "auto" }}>
          {doctors.length === 0 ? (
            <div className="clinical-empty">Kayıtlı hekim bulunamadı. Başlamak için yeni bir hekim ekleyin.</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", color: "#172b26", fontSize: "0.9rem" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid rgba(32,72,67,0.12)", textAlign: "left" }}>
                  <th style={{ padding: "12px 8px", color: "#667a76" }}>Ad Soyad</th>
                  <th style={{ padding: "12px 8px", color: "#667a76" }}>Uzmanlık Alanı</th>
                  <th style={{ padding: "12px 8px", color: "#667a76" }}>Durum</th>
                  <th style={{ padding: "12px 8px", textAlign: "right", color: "#667a76" }}>İşlemler</th>
                </tr>
              </thead>
              <tbody>
                {doctors.map((doc) => (
                  <tr key={doc.id} style={{ borderBottom: "1px solid rgba(32,72,67,0.06)", height: "48px" }}>
                    <td style={{ padding: "8px", fontWeight: "500" }}>{doc.full_name}</td>
                    <td style={{ padding: "8px" }}>{doc.specialty}</td>
                    <td style={{ padding: "8px" }}>
                      <span
                        className={`clinical-status ${doc.is_active ? "success" : "danger"}`}
                        style={{
                          display: "inline-block",
                          padding: "2px 8px",
                          borderRadius: "12px",
                          fontSize: "0.75rem",
                          background: doc.is_active ? "#e8f5ef" : "#fff0ee",
                          color: doc.is_active ? "#23835d" : "#bf4444",
                          border: "1px solid " + (doc.is_active ? "rgba(35,131,93,0.22)" : "rgba(191,68,68,0.2)")
                        }}
                      >
                        {doc.is_active ? "Aktif" : "Pasif"}
                      </span>
                    </td>
                    <td style={{ padding: "8px", textAlign: "right" }}>
                      <button
                        type="button"
                        onClick={() => startEdit(doc)}
                        style={{
                          background: "none",
                          border: "none",
                          color: "#1f6f68",
                          marginRight: "12px",
                          cursor: "pointer",
                          fontWeight: "600"
                        }}
                      >
                        Düzenle
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(doc.id)}
                        disabled={busy}
                        style={{
                          background: "none",
                          border: "none",
                          color: "#bf4444",
                          cursor: "pointer",
                          fontWeight: "600"
                        }}
                      >
                        Sil
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="clinical-form">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", color: "#667a76", marginBottom: "4px" }}>
                Hekim Adı Soyadı
              </label>
              <input
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Örn: Dr. Ahmet Yılmaz"
                required
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", color: "#667a76", marginBottom: "4px" }}>
                Uzmanlık Alanı
              </label>
              <input
                value={specialty}
                onChange={(e) => setSpecialty(e.target.value)}
                placeholder="Örn: Ortodonti veya Periodontoloji"
                required
              />
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "8px", margin: "10px 0" }}>
            <input
              type="checkbox"
              id="isActive"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              style={{ width: "auto", cursor: "pointer" }}
            />
            <label htmlFor="isActive" style={{ fontSize: "0.9rem", color: "#172b26", cursor: "pointer" }}>
              Aktif Hekim (Randevular için listelenir)
            </label>
          </div>

          <div style={{ display: "flex", gap: "10px", justifyContent: "flex-end" }}>
            <button
              type="button"
              onClick={() => setFormMode("list")}
              style={{ background: "#edf5f2", color: "#1f6f68", borderColor: "rgba(32,72,67,0.12)" }}
            >
              Vazgeç
            </button>
            <button type="submit" disabled={busy}>
              {busy ? "Kaydediliyor..." : "Hekimi Kaydet"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

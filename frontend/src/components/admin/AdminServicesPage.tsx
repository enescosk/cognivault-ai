import { useEffect, useState } from "react";
import { getServices, createService, updateService, deleteService, type ClinicService } from "../../api/client";
import { showToast } from "../ui/Toast";

interface Props {
  token: string;
}

export function AdminServicesPage({ token }: Props) {
  const [services, setServices] = useState<ClinicService[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  // Edit / Add Form State
  const [formMode, setFormMode] = useState<"list" | "add" | "edit">("list");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isActive, setIsActive] = useState(true);

  async function loadServices() {
    setLoading(true);
    try {
      const data = await getServices(token);
      setServices(data);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Hizmet listesi alınamadı.", "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadServices();
  }, [token]);

  function startAdd() {
    setFormMode("add");
    setEditingId(null);
    setName("");
    setDescription("");
    setIsActive(true);
  }

  function startEdit(srv: ClinicService) {
    setFormMode("edit");
    setEditingId(srv.id);
    setName(srv.name);
    setDescription(srv.description || "");
    setIsActive(srv.is_active);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      showToast("Lütfen hizmet adını doldurun.", "info");
      return;
    }

    setBusy(true);
    try {
      if (formMode === "add") {
        await createService(token, { name: name.trim(), description: description.trim() || undefined, is_active: isActive });
        showToast("Hizmet başarıyla eklendi.", "success");
      } else if (formMode === "edit" && editingId !== null) {
        await updateService(token, editingId, { name: name.trim(), description: description.trim() || undefined, is_active: isActive });
        showToast("Hizmet başarıyla güncellendi.", "success");
      }
      setFormMode("list");
      void loadServices();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Hizmet kaydedilemedi.", "error");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(id: number) {
    if (!window.confirm("Bu hizmeti silmek istediğinizden emin misiniz?")) return;
    setBusy(true);
    try {
      await deleteService(token, id);
      showToast("Hizmet başarıyla silindi.", "success");
      void loadServices();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Hizmet silinemedi.", "error");
    } finally {
      setBusy(false);
    }
  }

  if (loading && services.length === 0) {
    return <div className="clinical-empty">Klinik hizmetleri yükleniyor...</div>;
  }

  return (
    <div className="clinic-card admin-services-card">
      <div className="clinical-card-top">
        <div>
          <span>Klinik Hizmetleri</span>
          <h3>Sunulan Tıbbi ve Klinik Hizmetlerin Yönetimi</h3>
        </div>
        {formMode === "list" && (
          <button type="button" onClick={startAdd} className="patient-cta" style={{ background: "#1f6f68", color: "white", border: "0", padding: "8px 16px", borderRadius: "8px", fontWeight: "bold" }}>
            + Yeni Hizmet Ekle
          </button>
        )}
      </div>

      {formMode === "list" ? (
        <div style={{ overflowX: "auto" }}>
          {services.length === 0 ? (
            <div className="clinical-empty">Kayıtlı hizmet bulunamadı. Başlamak için yeni bir hizmet ekleyin.</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", color: "#172b26", fontSize: "0.9rem" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid rgba(32,72,67,0.12)", textAlign: "left" }}>
                  <th style={{ padding: "12px 8px", color: "#667a76" }}>Hizmet Adı</th>
                  <th style={{ padding: "12px 8px", color: "#667a76" }}>Açıklama</th>
                  <th style={{ padding: "12px 8px", color: "#667a76" }}>Durum</th>
                  <th style={{ padding: "12px 8px", textAlign: "right", color: "#667a76" }}>İşlemler</th>
                </tr>
              </thead>
              <tbody>
                {services.map((srv) => (
                  <tr key={srv.id} style={{ borderBottom: "1px solid rgba(32,72,67,0.06)", height: "48px" }}>
                    <td style={{ padding: "8px", fontWeight: "500" }}>{srv.name}</td>
                    <td style={{ padding: "8px", maxWidth: "300px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {srv.description || "Açıklama yok"}
                    </td>
                    <td style={{ padding: "8px" }}>
                      <span
                        className={`clinical-status ${srv.is_active ? "success" : "danger"}`}
                        style={{
                          display: "inline-block",
                          padding: "2px 8px",
                          borderRadius: "12px",
                          fontSize: "0.75rem",
                          background: srv.is_active ? "#e8f5ef" : "#fff0ee",
                          color: srv.is_active ? "#23835d" : "#bf4444",
                          border: "1px solid " + (srv.is_active ? "rgba(35,131,93,0.22)" : "rgba(191,68,68,0.2)")
                        }}
                      >
                        {srv.is_active ? "Aktif" : "Pasif"}
                      </span>
                    </td>
                    <td style={{ padding: "8px", textAlign: "right" }}>
                      <button
                        type="button"
                        onClick={() => startEdit(srv)}
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
                        onClick={() => handleDelete(srv.id)}
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
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "12px" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", color: "#667a76", marginBottom: "4px" }}>
                Hizmet / Poliklinik Adı
              </label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Örn: İmplant Tedavisi veya Diş Beyazlatma"
                required
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", color: "#667a76", marginBottom: "4px" }}>
                Hizmet Açıklaması
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Randevu alma akışında kullanılacak kısa poliklinik açıklaması..."
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
              Aktif Hizmet (Randevular için listelenir)
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
              {busy ? "Kaydediliyor..." : "Hizmeti Kaydet"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

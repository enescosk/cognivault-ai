import { useEffect, useState } from "react";
import { getDisclosures, createDisclosure, type KVKKDisclosure } from "../../api/client";
import { showToast } from "../ui/Toast";

interface Props {
  token: string;
}

export function AdminDisclosurePage({ token }: Props) {
  const [disclosures, setDisclosures] = useState<KVKKDisclosure[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  // Form State
  const [formMode, setFormMode] = useState<"list" | "new">("list");
  const [version, setVersion] = useState("");
  const [disclosureText, setDisclosureText] = useState("");
  const [isActive, setIsActive] = useState(true);

  async function loadDisclosures() {
    setLoading(true);
    try {
      const data = await getDisclosures(token);
      setDisclosures(data);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "KVKK aydınlatma geçmişi alınamadı.", "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadDisclosures();
  }, [token]);

  function startNew() {
    setFormMode("new");
    // Suggest next version number (e.g. current + 0.1 or increment)
    if (disclosures.length > 0) {
      const currentVer = disclosures[0].version;
      const num = parseFloat(currentVer);
      if (!isNaN(num)) {
        setVersion((num + 1.0).toFixed(1));
      } else {
        setVersion(currentVer + "_new");
      }
    } else {
      setVersion("1.0");
    }
    setDisclosureText("");
    setIsActive(true);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!version.trim() || !disclosureText.trim()) {
      showToast("Lütfen tüm alanları doldurun.", "info");
      return;
    }

    setBusy(true);
    try {
      await createDisclosure(token, {
        version: version.trim(),
        disclosure_text: disclosureText.trim(),
        is_active: isActive
      });
      showToast("Yeni KVKK Aydınlatma Metni sürümü başarıyla yayınlandı.", "success");
      setFormMode("list");
      void loadDisclosures();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "KVKK sürümü yayınlanamadı.", "error");
    } finally {
      setBusy(false);
    }
  }

  if (loading && disclosures.length === 0) {
    return <div className="clinical-empty">KVKK geçmişi yükleniyor...</div>;
  }

  return (
    <div className="clinic-card admin-disclosure-card">
      <div className="clinical-card-top">
        <div>
          <span>KVKK Aydınlatma ve Açık Rıza</span>
          <h3>Versiyonlanmış KVKK Aydınlatma Metni Yönetimi</h3>
        </div>
        {formMode === "list" && (
          <button type="button" onClick={startNew} className="patient-cta" style={{ background: "#1f6f68", color: "white", border: "0", padding: "8px 16px", borderRadius: "8px", fontWeight: "bold" }}>
            + Yeni Versiyon Yayınla
          </button>
        )}
      </div>

      {formMode === "list" ? (
        <div>
          {disclosures.length === 0 ? (
            <div className="clinical-empty">Yayınlanmış KVKK metni bulunamadı. Lütfen ilk versiyonu ekleyin.</div>
          ) : (
            <div style={{ display: "grid", gap: "16px" }}>
              <div style={{ background: "rgba(31,111,104,0.06)", border: "1px solid rgba(31,111,104,0.18)", borderRadius: "12px", padding: "16px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                  <span style={{ fontSize: "0.8rem", color: "#1f6f68", fontWeight: "bold", textTransform: "uppercase" }}>
                    Şu An Aktif Olan Versiyon: v{disclosures[0].version}
                  </span>
                  <span style={{ fontSize: "0.75rem", color: "#667a76" }}>
                    Yayınlanma: {new Date(disclosures[0].created_at).toLocaleDateString("tr-TR")}
                  </span>
                </div>
                <div style={{
                  background: "white",
                  border: "1px solid rgba(32,72,67,0.12)",
                  borderRadius: "8px",
                  padding: "12px",
                  maxHeight: "200px",
                  overflowY: "auto",
                  fontFamily: "monospace",
                  fontSize: "0.8rem",
                  whiteSpace: "pre-wrap",
                  color: "#172b26"
                }}>
                  {disclosures[0].disclosure_text}
                </div>
              </div>

              {disclosures.length > 1 && (
                <div>
                  <h4 style={{ fontSize: "0.95rem", color: "#172b26", marginBottom: "8px" }}>Versiyon Geçmişi</h4>
                  <table style={{ width: "100%", borderCollapse: "collapse", color: "#172b26", fontSize: "0.85rem" }}>
                    <thead>
                      <tr style={{ borderBottom: "2px solid rgba(32,72,67,0.12)", textAlign: "left" }}>
                        <th style={{ padding: "8px", color: "#667a76" }}>Sürüm</th>
                        <th style={{ padding: "8px", color: "#667a76" }}>Yayınlanma Tarihi</th>
                        <th style={{ padding: "8px", color: "#667a76" }}>Durum</th>
                      </tr>
                    </thead>
                    <tbody>
                      {disclosures.slice(1).map((disc) => (
                        <tr key={disc.id} style={{ borderBottom: "1px solid rgba(32,72,67,0.06)", height: "36px" }}>
                          <td style={{ padding: "6px 8px", fontWeight: "600" }}>v{disc.version}</td>
                          <td style={{ padding: "6px 8px" }}>{new Date(disc.created_at).toLocaleDateString("tr-TR")}</td>
                          <td style={{ padding: "6px 8px" }}>
                            <span style={{ fontSize: "0.75rem", color: "#667a76" }}>Pasif (Eski Sürüm)</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="clinical-form">
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "12px" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", color: "#667a76", marginBottom: "4px" }}>
                Sürüm Numarası (Version)
              </label>
              <input
                value={version}
                onChange={(e) => setVersion(e.target.value)}
                placeholder="Örn: 1.0 veya 2.1"
                required
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", color: "#667a76", marginBottom: "4px" }}>
                Aydınlatma ve Açık Rıza Metni
              </label>
              <textarea
                value={disclosureText}
                onChange={(e) => setDisclosureText(e.target.value)}
                placeholder="KVKK m.10 kapsamında hastaları bilgilendiren yasal aydınlatma metnini buraya yapıştırın..."
                style={{ minHeight: "220px", fontFamily: "monospace" }}
                required
              />
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "8px", margin: "10px 0" }}>
            <input
              type="checkbox"
              id="isDisclosureActive"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              style={{ width: "auto", cursor: "pointer" }}
            />
            <label htmlFor="isDisclosureActive" style={{ fontSize: "0.9rem", color: "#172b26", cursor: "pointer" }}>
              Bu versiyonu hemen aktif yap (Önceki aktif sürüm pasif hale getirilir)
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
              {busy ? "Yayınlanıyor..." : "Yeni Sürümü Yayınla"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

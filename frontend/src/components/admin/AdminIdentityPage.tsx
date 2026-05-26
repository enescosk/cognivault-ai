import { useEffect, useState } from "react";
import { getBranding, updateBranding } from "../../api/client";
import { showToast } from "../ui/Toast";

interface Props {
  token: string;
}

export function AdminIdentityPage({ token }: Props) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [headline, setHeadline] = useState("");
  const [subHeadline, setSubHeadline] = useState("");
  const [logoUrl, setLogoUrl] = useState("");
  const [primaryColor, setPrimaryColor] = useState("");
  const [accentColor, setAccentColor] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [publicAddress, setPublicAddress] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const res = await getBranding(token);
        const b = res.branding || {};
        setHeadline(b.headline || "");
        setSubHeadline(b.sub_headline || "");
        setLogoUrl(b.logo_url || "");
        setPrimaryColor(b.primary_color || "");
        setAccentColor(b.accent_color || "");
        setContactPhone(b.contact_phone || "");
        setPublicAddress(b.public_address || "");
      } catch (err) {
        showToast(err instanceof Error ? err.message : "Kimlik bilgileri yüklenemedi.", "error");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [token]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await updateBranding(token, {
        headline,
        sub_headline: subHeadline,
        logo_url: logoUrl,
        primary_color: primaryColor,
        accent_color: accentColor,
        contact_phone: contactPhone,
        public_address: publicAddress,
      });
      showToast("Klinik kimlik ve tasarım bilgileri başarıyla güncellendi.", "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Bilgiler kaydedilemedi.", "error");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="clinical-empty">Klinik kimlik bilgileri yükleniyor...</div>;
  }

  return (
    <div className="clinic-card admin-identity-card">
      <div className="clinical-card-top">
        <div>
          <span>Tasarım ve Kimlik</span>
          <h3>Klinik Görsel ve İletişim Ayarları</h3>
        </div>
      </div>
      <form onSubmit={handleSave} className="clinical-form">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <div>
            <label style={{ display: "block", fontSize: "0.8rem", color: "#667a76", marginBottom: "4px" }}>
              Klinik Karşılama Başlığı (Headline)
            </label>
            <input
              value={headline}
              onChange={(e) => setHeadline(e.target.value)}
              placeholder="Örn: Sağlığınız İçin Güvenilir Tercih"
              required
            />
          </div>
          <div>
            <label style={{ display: "block", fontSize: "0.8rem", color: "#667a76", marginBottom: "4px" }}>
              Klinik Karşılama Alt Başlığı (Sub Headline)
            </label>
            <input
              value={subHeadline}
              onChange={(e) => setSubHeadline(e.target.value)}
              placeholder="Örn: Diş hekimliğinde uzman kadromuzla yanınızdayız."
              required
            />
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <div>
            <label style={{ display: "block", fontSize: "0.8rem", color: "#667a76", marginBottom: "4px" }}>
              Logo Görsel Bağlantısı (URL)
            </label>
            <input
              value={logoUrl}
              onChange={(e) => setLogoUrl(e.target.value)}
              placeholder="https://example.com/logo.png"
            />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", color: "#667a76", marginBottom: "4px" }}>
                Ana Renk (Primary)
              </label>
              <div style={{ display: "flex", gap: "6px" }}>
                <input
                  type="color"
                  value={primaryColor || "#319795"}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                  style={{ width: "40px", padding: "2px", height: "40px", cursor: "pointer" }}
                />
                <input
                  value={primaryColor}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                  placeholder="#319795"
                  style={{ flex: 1 }}
                />
              </div>
            </div>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", color: "#667a76", marginBottom: "4px" }}>
                Vurgu Rengi (Accent)
              </label>
              <div style={{ display: "flex", gap: "6px" }}>
                <input
                  type="color"
                  value={accentColor || "#2b6cb0"}
                  onChange={(e) => setAccentColor(e.target.value)}
                  style={{ width: "40px", padding: "2px", height: "40px", cursor: "pointer" }}
                />
                <input
                  value={accentColor}
                  onChange={(e) => setAccentColor(e.target.value)}
                  placeholder="#2b6cb0"
                  style={{ flex: 1 }}
                />
              </div>
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <div>
            <label style={{ display: "block", fontSize: "0.8rem", color: "#667a76", marginBottom: "4px" }}>
              İrtibat Telefonu
            </label>
            <input
              value={contactPhone}
              onChange={(e) => setContactPhone(e.target.value)}
              placeholder="+90 (212) 555 00 00"
            />
          </div>
          <div>
            <label style={{ display: "block", fontSize: "0.8rem", color: "#667a76", marginBottom: "4px" }}>
              Klinik Açık Adresi
            </label>
            <input
              value={publicAddress}
              onChange={(e) => setPublicAddress(e.target.value)}
              placeholder="Karanfil Sok. No: 12, Levent, İstanbul"
            />
          </div>
        </div>

        <div style={{ marginTop: "14px", display: "flex", justifyContent: "flex-end" }}>
          <button type="submit" disabled={saving} style={{ minWidth: "140px" }}>
            {saving ? "Kaydediliyor..." : "Ayarları Kaydet"}
          </button>
        </div>
      </form>
    </div>
  );
}

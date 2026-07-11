import { useState } from "react";
import { AdminIdentityPage } from "./admin/AdminIdentityPage";
import { AdminDoctorsPage } from "./admin/AdminDoctorsPage";
import { AdminServicesPage } from "./admin/AdminServicesPage";
import { AdminDisclosurePage } from "./admin/AdminDisclosurePage";
import { AdminVoicePage } from "./admin/AdminVoicePage";

interface Props {
  token: string;
}

type TabType = "identity" | "voice" | "doctors" | "services" | "disclosure";

export function ClinicAdminPanel({ token }: Props) {
  const [activeTab, setActiveTab] = useState<TabType>("identity");

  return (
    <div className="clinical-panel boutique-clinic-panel" style={{ padding: "20px", display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Hero Section */}
      <section className="clinic-hero" style={{ marginBottom: "0px" }}>
        <div className="clinic-hero-copy" style={{ flex: 1, padding: "20px" }}>
          <div className="clinical-kicker">CogniVault Clinical OS</div>
          <h2 style={{ fontSize: "2rem", margin: "4px 0 8px" }}>Klinik Yönetim & KVKK Kontrol Kokpiti</h2>
          <p style={{ fontSize: "0.95rem", margin: 0, color: "#4f645f" }}>
            Hekimler, klinik hizmetleri, tasarım kimliği ve yasal KVKK uyumluluk metinlerini yönetebileceğiniz merkez panel.
          </p>
        </div>
      </section>

      {/* Tabs Navigation */}
      <div className="clinical-segmented" style={{ gridTemplateColumns: "repeat(5, minmax(0, 1fr))", maxWidth: "980px" }}>
        <button
          type="button"
          className={activeTab === "identity" ? "active" : ""}
          onClick={() => setActiveTab("identity")}
          style={{ padding: "10px", fontSize: "0.85rem", fontWeight: "bold" }}
        >
          Tasarım & Kimlik
        </button>
        <button
          type="button"
          className={activeTab === "voice" ? "active" : ""}
          onClick={() => setActiveTab("voice")}
          style={{ padding: "10px", fontSize: "0.85rem", fontWeight: "bold" }}
        >
          Ses Provider
        </button>
        <button
          type="button"
          className={activeTab === "doctors" ? "active" : ""}
          onClick={() => setActiveTab("doctors")}
          style={{ padding: "10px", fontSize: "0.85rem", fontWeight: "bold" }}
        >
          Hekim Yönetimi
        </button>
        <button
          type="button"
          className={activeTab === "services" ? "active" : ""}
          onClick={() => setActiveTab("services")}
          style={{ padding: "10px", fontSize: "0.85rem", fontWeight: "bold" }}
        >
          Hizmet Yönetimi
        </button>
        <button
          type="button"
          className={activeTab === "disclosure" ? "active" : ""}
          onClick={() => setActiveTab("disclosure")}
          style={{ padding: "10px", fontSize: "0.85rem", fontWeight: "bold" }}
        >
          KVKK Metinleri
        </button>
      </div>

      {/* Active Tab View */}
      <section style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        {activeTab === "identity" && <AdminIdentityPage token={token} />}
        {activeTab === "voice" && <AdminVoicePage token={token} />}
        {activeTab === "doctors" && <AdminDoctorsPage token={token} />}
        {activeTab === "services" && <AdminServicesPage token={token} />}
        {activeTab === "disclosure" && <AdminDisclosurePage token={token} />}
      </section>
    </div>
  );
}

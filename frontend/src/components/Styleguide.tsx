import type { CSSProperties, ReactNode } from "react";

import type { ShadowReview } from "../types/api";
import { ShadowReviewCard } from "./clinical/ShadowReviewCard";
import { Badge, Button, Card, Field, Panel, StatusDot } from "./ui";

/**
 * Canlı tasarım kılavuzu — /styleguide (public).
 * CogniVault token'ları ve yeniden kullanılabilir primitive'lerin tek ekrandaki
 * vitrini. Yeni ekranlar buradaki parçalarla kurulur. Bkz. frontend/DESIGN_SYSTEM.md
 */

const wrap: CSSProperties = { maxWidth: 940, margin: "0 auto", padding: "56px 24px 120px" };
const grid = (min = 150): CSSProperties => ({
  display: "grid",
  gridTemplateColumns: `repeat(auto-fill, minmax(${min}px, 1fr))`,
  gap: 12,
});
const rowWrap: CSSProperties = { display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" };

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section style={{ marginTop: 40 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 16 }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "1.05rem", color: "var(--text)", letterSpacing: "-0.01em" }}>
          {title}
        </h2>
        {hint && <span style={{ fontSize: "0.74rem", color: "var(--text-3)" }}>{hint}</span>}
      </div>
      {children}
    </section>
  );
}

const colorTokens: { token: string; label: string }[] = [
  { token: "--bg", label: "Zemin" },
  { token: "--surface", label: "Yüzey" },
  { token: "--border", label: "Çerçeve" },
  { token: "--text", label: "Metin" },
  { token: "--text-2", label: "Metin 2" },
  { token: "--accent", label: "Accent" },
  { token: "--green", label: "Onay" },
  { token: "--amber", label: "Bekleyen" },
  { token: "--red", label: "Acil / İptal" },
  { token: "--purple", label: "AI / Özel" },
];

const radii = [
  { token: "--radius-sm", px: 8 },
  { token: "--radius", px: 14 },
  { token: "--radius-lg", px: 20 },
  { token: "--radius-xl", px: 28 },
];

const demoReview = {
  id: 1,
  clinic_id: 1,
  conversation_id: 1,
  patient_message_id: 1,
  draft_reply:
    "Çok geçmiş olsun. Ağrı ve şişlik bilgisini öncelikli not aldım; size en yakın uygun slotu kontrol ediyorum. Şikayet hızla artarsa operatöre öncelikli aktarıyorum.",
  intent: "medical_emergency",
  confidence_score: 0.62,
  risk_reason: "low_confidence_intent",
  status: "pending",
  persona_name: "Klinik Asistan",
  channel: "whatsapp",
  final_reply: null,
  metadata_json: {
    data: {
      privacy_guardrail: {
        data_residency_mode: "tr_local_first",
        data_classes: ["special_category_health_data", "contact_data"],
        human_review_reasons: ["medical_emergency_requires_human_escalation"],
        redacted_preview: "Dün geceden beri azı dişim çok ağrıyor, numaram [REDACTED]",
        auto_send_allowed: false,
      },
    },
  },
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
} satisfies ShadowReview;

export function Styleguide() {
  return (
    <div style={wrap}>
      <header style={{ borderBottom: "1px solid var(--border)", paddingBottom: 24 }}>
        <div style={{ ...rowWrap, justifyContent: "space-between" }}>
          <div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.7rem", letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--accent)" }}>
              CogniVault · Tasarım Sistemi
            </div>
            <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "2rem", color: "var(--text)", letterSpacing: "-0.02em", marginTop: 6 }}>
              Styleguide
            </h1>
            <p style={{ color: "var(--text-2)", fontSize: "0.9rem", maxWidth: 540, marginTop: 8 }}>
              Tüm ekranlar bu token'lar ve primitive'lerle kurulur. Yeni renk, font ya da
              sınıf icat edilmez — buradakiler dizilir.
            </p>
          </div>
          <Badge tone="accent">v1</Badge>
        </div>
      </header>

      {/* RENK */}
      <Section title="Renk" hint="koyu, premium, klinik güven">
        <div style={grid(150)}>
          {colorTokens.map((c) => (
            <div key={c.token}>
              <div
                style={{
                  height: 56,
                  borderRadius: "var(--radius)",
                  background: `var(${c.token})`,
                  border: "1px solid var(--border)",
                }}
              />
              <div style={{ marginTop: 8, fontSize: "0.8rem", color: "var(--text)" }}>{c.label}</div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.66rem", color: "var(--text-3)" }}>{c.token}</div>
            </div>
          ))}
        </div>
      </Section>

      {/* TİPOGRAFİ */}
      <Section title="Tipografi" hint="Syne · DM Sans · DM Mono">
        <Card>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "1.6rem", color: "var(--text)", letterSpacing: "-0.02em" }}>
            Syne — başlıklar ve vurgu
          </div>
          <p style={{ fontFamily: "var(--font-body)", color: "var(--text-2)", marginTop: 12, lineHeight: 1.6 }}>
            DM Sans — gövde metni. Hasta ile doğal, sakin ve güven veren bir dil. Bol boşluk,
            net hiyerarşi, gereksiz çizgi yok.
          </p>
          <div style={{ fontFamily: "var(--font-mono)", color: "var(--accent)", marginTop: 14, fontSize: "0.95rem" }}>
            DM Mono → AC-2847 · 09:45 · %92 güven
          </div>
        </Card>
      </Section>

      {/* BUTON */}
      <Section title="Buton" hint="primary kıt ve anlamlı kullanılır">
        <div style={rowWrap}>
          <Button variant="primary">Hekime onayla</Button>
          <Button variant="ghost">Detay</Button>
          <Button variant="subtle">Vazgeç</Button>
          <Button variant="danger">İptal et</Button>
          <Button variant="primary" disabled>
            Pasif
          </Button>
        </div>
        <div style={{ ...rowWrap, marginTop: 12 }}>
          <Button variant="ghost" size="sm">
            Küçük
          </Button>
          <Button variant="ghost">Orta</Button>
          <Button variant="ghost" size="lg">
            Büyük
          </Button>
        </div>
      </Section>

      {/* ROZET & DURUM */}
      <Section title="Rozet & Durum" hint="renk + şekil; renk körlüğü için ikisi birden">
        <div style={rowWrap}>
          <Badge tone="accent">Endodonti</Badge>
          <Badge tone="green">Onaylı</Badge>
          <Badge tone="amber">Bekliyor</Badge>
          <Badge tone="red">Acil</Badge>
          <Badge tone="purple">AI taslağı</Badge>
          <Badge tone="neutral">Genel</Badge>
        </div>
        <div style={{ ...rowWrap, marginTop: 16 }}>
          <StatusDot tone="green">Çalışıyor</StatusDot>
          <StatusDot tone="amber">Orta öncelik</StatusDot>
          <StatusDot tone="red" pulse>
            Acil — insana yükseltildi
          </StatusDot>
          <StatusDot tone="accent">Yerel işleniyor</StatusDot>
        </div>
      </Section>

      {/* KART */}
      <Section title="Kart">
        <div style={grid(220)}>
          <Card hover>
            <div style={{ color: "var(--text)", fontWeight: 600 }}>Standart kart</div>
            <div style={{ color: "var(--text-2)", fontSize: "0.84rem", marginTop: 6 }}>Yüzey + ince çerçeve, hover'da hafif aydınlanır.</div>
          </Card>
          <Card accent>
            <div style={{ color: "var(--text)", fontWeight: 600 }}>Vurgulu kart</div>
            <div style={{ color: "var(--text-2)", fontSize: "0.84rem", marginTop: 6 }}>Aktif / seçili durumu işaret eder.</div>
          </Card>
        </div>
      </Section>

      {/* FORM */}
      <Section title="Form">
        <div style={{ ...grid(240), maxWidth: 520 }}>
          <Field id="sg-name" label="Hasta adı" placeholder="Ad Soyad" />
          <Field id="sg-phone" label="Telefon" placeholder="+90 5xx xxx xx xx" hint="KVKK: maskelenir, ham PII saklanmaz" />
        </div>
      </Section>

      {/* KOMPOZİSYON ÖRNEĞİ */}
      <Section title="Kompozisyon örneği" hint="primitive'lerle gerçek bir klinik kartı">
        <Panel
          title="Gelen triyaj"
          subtitle="Yerinde işlendi · hekim onayı bekliyor"
          actions={<Badge tone="purple">Shadow Mode</Badge>}
          footer="Karar denetim izine yazıldı · ham veri klinikten çıkmadı"
        >
          <Card accent>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
              <div>
                <div style={rowWrap}>
                  <Badge tone="accent">Endodonti</Badge>
                  <StatusDot tone="amber">Orta öncelik</StatusDot>
                </div>
                <p style={{ color: "var(--text)", marginTop: 10, fontSize: "0.92rem" }}>
                  “Dün geceden beri azı dişim çok ağrıyor, sıcakta artıyor.”
                </p>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.72rem", color: "var(--text-3)", marginTop: 8 }}>
                  AC-2847 · güven %88 · 09:45
                </div>
              </div>
            </div>
            <div style={{ ...rowWrap, marginTop: 14 }}>
              <Button variant="primary" size="sm">
                Hekime onayla
              </Button>
              <Button variant="ghost" size="sm">
                Düzelt
              </Button>
            </div>
          </Card>
        </Panel>
      </Section>

      {/* KARAR KARTI */}
      <Section title="Karar Kartı" hint="governance + çekimserlik + Shadow Mode — gerçek backend alanları">
        <div style={{ maxWidth: 560 }}>
          <ShadowReviewCard
            review={demoReview}
            editing={false}
            editedReply=""
            busy={false}
            onEditedReplyChange={() => {}}
            onApprove={() => {}}
            onStartEdit={() => {}}
            onSubmitEdit={() => {}}
            onReject={() => {}}
          />
        </div>
      </Section>

      {/* ŞEKİL */}
      <Section title="Köşe yarıçapı">
        <div style={rowWrap}>
          {radii.map((r) => (
            <div key={r.token} style={{ textAlign: "center" }}>
              <div
                style={{
                  width: 76,
                  height: 76,
                  borderRadius: `var(${r.token})`,
                  background: "var(--surface)",
                  border: "1px solid var(--border-hover)",
                }}
              />
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.66rem", color: "var(--text-3)", marginTop: 8 }}>{r.px}px</div>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}

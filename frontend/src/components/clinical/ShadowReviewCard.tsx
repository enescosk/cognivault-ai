import type { ShadowReview } from "../../types/api";
import { Badge, Button } from "../ui";

/**
 * Karar Kartı — bir ShadowReview'ı (hekim onayı bekleyen YZ taslağı) governance
 * hikâyesiyle birlikte gösterir. Tamamen sunum odaklı: veri ClinicalPanel'den,
 * kararlar callback'lerle gelir. Backend alanları (clinical_service.py):
 *   confidence_score · risk_reason · metadata_json.data.privacy_guardrail
 * Bir shadow review zaten "güven eşiğin altında VEYA insan-yükseltme gerekli"
 * olduğu için vardır — yani kartın varlığı çekimserlik/eskalasyon kanıtıdır.
 */

interface ShadowReviewCardProps {
  review: ShadowReview;
  editing: boolean;
  editedReply: string;
  busy: boolean;
  onEditedReplyChange: (value: string) => void;
  onApprove: () => void;
  onStartEdit: () => void;
  onSubmitEdit: () => void;
  onReject: () => void;
}

type Tone = "neutral" | "accent" | "green" | "amber" | "red" | "purple";

const STATUS_TONE: Record<string, Tone> = {
  pending: "amber",
  waiting_human: "amber",
  approved: "green",
  edited: "accent",
  rejected: "red",
};
const STATUS_LABEL: Record<string, string> = {
  pending: "Onay bekliyor",
  waiting_human: "Onay bekliyor",
  approved: "Onaylandı",
  edited: "Düzeltildi",
  rejected: "Reddedildi",
};
const DATA_CLASS_LABEL: Record<string, string> = {
  special_category_health_data: "Özel nitelikli sağlık",
  financial_or_insurance_data: "Finansal / sigorta",
  national_identifier: "Kimlik (TCKN)",
  contact_data: "İletişim",
  voice_interaction_metadata: "Ses metadata",
};
const RESIDENCY_LABEL: Record<string, string> = {
  tr_local_first: "Yerel işlendi · ham veri çıkmadı",
  hybrid_explicit_consent: "Hibrit · açık rıza ile",
};

const humanize = (value: string) => value.replace(/_/g, " ");

function readGovernance(review: ShadowReview) {
  const meta = review.metadata_json as Record<string, unknown> | null | undefined;
  const data = (meta?.data ?? {}) as Record<string, unknown>;
  const gov = (data.privacy_guardrail ?? {}) as Record<string, unknown>;
  return {
    residency: typeof gov.data_residency_mode === "string" ? gov.data_residency_mode : undefined,
    dataClasses: Array.isArray(gov.data_classes) ? (gov.data_classes as string[]) : [],
    redacted: typeof gov.redacted_preview === "string" ? gov.redacted_preview : undefined,
  };
}

export function ShadowReviewCard({
  review,
  editing,
  editedReply,
  busy,
  onEditedReplyChange,
  onApprove,
  onStartEdit,
  onSubmitEdit,
  onReject,
}: ShadowReviewCardProps) {
  const gov = readGovernance(review);
  const confidence = Math.round((review.confidence_score ?? 0) * 100);
  const meterTone = confidence >= 80 ? "green" : confidence >= 60 ? "amber" : "red";
  const isPending = review.status === "pending" || review.status === "waiting_human";
  const statusTone = STATUS_TONE[review.status] ?? "neutral";
  const statusLabel = STATUS_LABEL[review.status] ?? review.status;
  const hasGovernance = Boolean(gov.residency || gov.dataClasses.length || gov.redacted);

  return (
    <article className="ui-card shadow-card">
      <div className="shadow-card-head">
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <Badge tone="accent">{humanize(review.intent)}</Badge>
          {review.persona_name && <span className="ui-mono shadow-card-meta">{review.persona_name}</span>}
        </div>
        <Badge tone={statusTone}>{statusLabel}</Badge>
      </div>

      <div className="shadow-card-conf">
        <span className="shadow-card-conf-label">Güven</span>
        <div className="ui-meter">
          <div className={`ui-meter-fill ui-meter-fill--${meterTone}`} style={{ width: `${confidence}%` }} />
        </div>
        <span className="ui-mono shadow-card-conf-val">%{confidence}</span>
        {isPending && (
          <span className="ui-status" style={{ marginLeft: "auto" }}>
            <span className="ui-dot ui-dot--amber ui-dot--pulse" />
            insana yükseltildi
          </span>
        )}
      </div>

      {review.risk_reason && (
        <div className="shadow-card-reason">
          <span className="shadow-card-reason-k">Neden</span>
          {humanize(review.risk_reason)}
        </div>
      )}

      <div className="shadow-card-draft">
        <Badge tone="purple">AI taslağı · teşhis yok</Badge>
        {editing ? (
          <textarea
            className="ui-input shadow-card-textarea"
            value={editedReply}
            onChange={(event) => onEditedReplyChange(event.target.value)}
            rows={4}
          />
        ) : (
          <p className="shadow-card-draft-text">{review.draft_reply}</p>
        )}
      </div>

      {hasGovernance && (
        <div className="shadow-card-gov">
          {gov.residency && (
            <span className="ui-status">
              <span className="ui-dot ui-dot--green" />
              {RESIDENCY_LABEL[gov.residency] ?? humanize(gov.residency)}
            </span>
          )}
          {gov.dataClasses.map((cls) => (
            <Badge key={cls} tone="neutral">
              {DATA_CLASS_LABEL[cls] ?? humanize(cls)}
            </Badge>
          ))}
          {gov.redacted && (
            <span className="shadow-card-gov-redacted ui-mono" title="LLM'e maskeli giden önizleme">
              maskeli: {gov.redacted}
            </span>
          )}
        </div>
      )}

      <div className="shadow-card-actions">
        {editing ? (
          <Button variant="primary" size="sm" onClick={onSubmitEdit} disabled={busy || !editedReply.trim()}>
            Düzeltmeyi gönder
          </Button>
        ) : (
          <Button variant="primary" size="sm" onClick={onApprove} disabled={busy}>
            Onayla
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={onStartEdit} disabled={busy}>
          Düzenle
        </Button>
        <Button variant="danger" size="sm" onClick={onReject} disabled={busy}>
          Reddet
        </Button>
      </div>
    </article>
  );
}

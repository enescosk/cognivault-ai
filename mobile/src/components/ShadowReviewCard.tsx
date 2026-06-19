import { StyleSheet, Text, TextInput, View } from "react-native";

import { readGovernance, type ShadowReview } from "../api";
import { C, MONO, R } from "../theme";
import { Badge, Button, Meter, StatusRow, type Tone } from "./ui";

type Props = {
  review: ShadowReview;
  editing: boolean;
  editedReply: string;
  busy: boolean;
  onEditedReplyChange: (value: string) => void;
  onApprove: () => void;
  onStartEdit: () => void;
  onSubmitEdit: () => void;
  onReject: () => void;
};

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
}: Props) {
  const governance = readGovernance(review);
  const confidence = Math.round((review.confidence_score ?? 0) * 100);
  const isPending = review.status === "pending" || review.status === "waiting_human";
  const hasGovernance = Boolean(
    governance.residency || governance.dataClasses.length || governance.redacted,
  );

  return (
    <View style={styles.card}>
      <View style={styles.head}>
        <View style={styles.identity}>
          <Badge tone="accent">{humanize(review.intent)}</Badge>
          {review.persona_name ? <Text style={styles.persona}>{review.persona_name}</Text> : null}
        </View>
        <Badge tone={STATUS_TONE[review.status] ?? "neutral"}>
          {STATUS_LABEL[review.status] ?? humanize(review.status)}
        </Badge>
      </View>

      <View style={styles.confidence}>
        <Text style={styles.mutedLabel}>Güven</Text>
        <Meter value={confidence} />
        <Text style={styles.confidenceValue}>%{confidence}</Text>
      </View>
      {isPending ? <StatusRow tone="amber">İnsana yükseltildi</StatusRow> : null}

      {review.risk_reason ? (
        <Text style={styles.reason}>
          <Text style={styles.reasonKey}>NEDEN  </Text>
          {humanize(review.risk_reason)}
        </Text>
      ) : null}

      <View style={styles.draft}>
        <Badge tone="purple">AI taslağı · teşhis yok</Badge>
        {editing ? (
          <TextInput
            accessibilityLabel="AI yanıt taslağını düzenle"
            multiline
            onChangeText={onEditedReplyChange}
            placeholder="Hastaya gönderilecek yanıt"
            placeholderTextColor={C.text3}
            style={styles.editor}
            textAlignVertical="top"
            value={editedReply}
          />
        ) : (
          <Text style={styles.draftText}>{review.draft_reply}</Text>
        )}
      </View>

      {hasGovernance ? (
        <View style={styles.governance}>
          {governance.residency ? (
            <StatusRow tone="green">
              {RESIDENCY_LABEL[governance.residency] ?? humanize(governance.residency)}
            </StatusRow>
          ) : null}
          <View style={styles.badges}>
            {governance.dataClasses.map((dataClass) => (
              <Badge key={dataClass}>{DATA_CLASS_LABEL[dataClass] ?? humanize(dataClass)}</Badge>
            ))}
          </View>
          {governance.redacted ? (
            <Text numberOfLines={3} style={styles.redacted}>
              maskeli: {governance.redacted}
            </Text>
          ) : null}
        </View>
      ) : null}

      <View style={styles.actions}>
        {editing ? (
          <Button
            disabled={!editedReply.trim()}
            loading={busy}
            onPress={onSubmitEdit}
            style={styles.primaryAction}
          >
            Düzeltmeyi gönder
          </Button>
        ) : (
          <Button loading={busy} onPress={onApprove} style={styles.primaryAction}>
            Onayla
          </Button>
        )}
        <Button disabled={busy} onPress={onStartEdit} variant="ghost">
          {editing ? "Vazgeç" : "Düzenle"}
        </Button>
        <Button disabled={busy} onPress={onReject} variant="danger">
          Reddet
        </Button>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: C.surface,
    borderColor: C.border,
    borderRadius: R.lg,
    borderWidth: 1,
    padding: 16,
    gap: 13,
    shadowColor: "#173d36",
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.07,
    shadowRadius: 18,
    elevation: 2,
  },
  head: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 10 },
  identity: { flex: 1, gap: 7, alignItems: "flex-start" },
  persona: { color: C.text3, fontFamily: MONO, fontSize: 11 },
  confidence: { flexDirection: "row", alignItems: "center", gap: 10 },
  mutedLabel: { color: C.text2, fontSize: 12 },
  confidenceValue: { color: C.text, fontFamily: MONO, fontSize: 12, minWidth: 35 },
  reason: { color: C.text2, fontSize: 13, lineHeight: 19 },
  reasonKey: { color: C.text3, fontFamily: MONO, fontSize: 10, letterSpacing: 0.5 },
  draft: {
    backgroundColor: C.purpleSoft,
    borderColor: "rgba(107,70,193,0.16)",
    borderRadius: R.sm,
    borderWidth: 1,
    gap: 10,
    padding: 13,
  },
  draftText: { color: C.text, fontSize: 15, lineHeight: 23 },
  editor: {
    minHeight: 116,
    backgroundColor: C.surface,
    borderColor: C.borderStrong,
    borderRadius: R.sm,
    borderWidth: 1,
    color: C.text,
    fontSize: 15,
    lineHeight: 22,
    padding: 12,
  },
  governance: { borderTopColor: C.border, borderTopWidth: 1, gap: 10, paddingTop: 13 },
  badges: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
  redacted: {
    alignSelf: "flex-start",
    backgroundColor: C.surfaceAlt,
    borderColor: C.border,
    borderRadius: 7,
    borderWidth: 1,
    color: C.text2,
    fontFamily: MONO,
    fontSize: 10,
    lineHeight: 15,
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  primaryAction: { flexGrow: 1 },
});

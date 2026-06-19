import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { api, type ClinicalOverview, type DecisionStatus, type ShadowReview } from "../api";
import { useAuth } from "../auth";
import { ShadowReviewCard } from "../components/ShadowReviewCard";
import { Badge, EmptyState } from "../components/ui";
import { C, R } from "../theme";

export function QueueScreen() {
  const { token, user, logout } = useAuth();
  const [overview, setOverview] = useState<ClinicalOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editedReply, setEditedReply] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(
    async (quiet = false) => {
      if (!token) return;
      if (!quiet) setLoading(true);
      setError(null);
      try {
        setOverview(await api.overview(token));
      } catch {
        setError("Onay kuyruğu alınamadı. Backend bağlantısını kontrol et.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [token],
  );

  useEffect(() => {
    void load();
  }, [load]);

  function startEdit(review: ShadowReview) {
    if (editingId === review.id) {
      setEditingId(null);
      setEditedReply("");
      return;
    }
    setEditingId(review.id);
    setEditedReply(review.final_reply || review.draft_reply);
  }

  async function decide(review: ShadowReview, status: DecisionStatus) {
    if (!token || busyId !== null) return;
    const finalReply = status === "edited" ? editedReply.trim() : undefined;
    if (status === "edited" && !finalReply) return;

    const previous = overview;
    setBusyId(review.id);
    setError(null);
    setOverview((current) =>
      current
        ? {
            ...current,
            metrics: {
              ...current.metrics,
              pending_shadow_reviews: Math.max(0, current.metrics.pending_shadow_reviews - 1),
            },
            shadow_reviews: current.shadow_reviews.filter((item) => item.id !== review.id),
          }
        : current,
    );

    try {
      await api.decide(review.id, token, status, finalReply);
      setEditingId(null);
      setEditedReply("");
      await load(true);
    } catch {
      setOverview(previous);
      setError("Karar kaydedilemedi. Lütfen tekrar dene.");
    } finally {
      setBusyId(null);
    }
  }

  function refresh() {
    setRefreshing(true);
    void load(true);
  }

  if (loading && !overview) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={C.primary} size="large" />
        <Text style={styles.loadingText}>Hekim kuyruğu hazırlanıyor…</Text>
      </View>
    );
  }

  const reviews = overview?.shadow_reviews ?? [];
  const pending = overview?.metrics.pending_shadow_reviews ?? reviews.length;
  const doctorName = overview?.viewer.doctor_name || user?.full_name || "Hekim";
  const firstName = doctorName.replace(/^Dr\.\s*/i, "").split(" ")[0];

  return (
    <View style={styles.screen}>
      <FlatList
        contentContainerStyle={styles.listContent}
        data={reviews}
        keyExtractor={(item) => String(item.id)}
        ListHeaderComponent={
          <View style={styles.headerWrap}>
            <View style={styles.topbar}>
              <View style={styles.brand}>
                <View style={styles.brandMark}>
                  <Text style={styles.brandLetter}>C</Text>
                </View>
                <View>
                  <Text style={styles.brandName}>Cogni Klinik</Text>
                  <Text style={styles.clinicName}>
                    {overview?.metrics.clinic_name ?? "Klinik karar alanı"}
                  </Text>
                </View>
              </View>
              <Pressable accessibilityRole="button" onPress={() => void logout()} style={styles.logout}>
                <Text style={styles.logoutText}>Çıkış</Text>
              </Pressable>
            </View>

            <View style={styles.welcome}>
              <View style={styles.welcomeCopy}>
                <Text style={styles.eyebrow}>HEKIM ONAY KUYRUĞU</Text>
                <Text style={styles.title}>Günaydın, {firstName}</Text>
                <Text style={styles.subtitle}>
                  {overview?.viewer.specialty
                    ? `${overview.viewer.specialty} · yalnızca sana atanmış kararlar`
                    : "AI’nin çekimser kaldığı yanıtlar klinik kararını bekliyor."}
                </Text>
              </View>
              <View style={styles.pendingBox}>
                <Text style={styles.pendingValue}>{pending}</Text>
                <Text style={styles.pendingLabel}>bekleyen karar</Text>
              </View>
            </View>

            <View style={styles.sectionHead}>
              <Text style={styles.sectionTitle}>İncelenecek taslaklar</Text>
              <Badge tone={pending ? "amber" : "green"}>{pending ? `${pending} bekliyor` : "Kuyruk temiz"}</Badge>
            </View>
            {error ? (
              <Pressable onPress={refresh} style={styles.errorBox}>
                <Text style={styles.errorText}>{error} · Yenilemek için dokun.</Text>
              </Pressable>
            ) : null}
          </View>
        }
        ListEmptyComponent={
          <EmptyState
            body="Yeni bir riskli veya düşük güvenli AI taslağı geldiğinde burada görünecek."
            icon={<Text style={styles.check}>✓</Text>}
            title="Tüm kararlar tamam"
          />
        }
        refreshControl={<RefreshControl colors={[C.primary]} onRefresh={refresh} refreshing={refreshing} tintColor={C.primary} />}
        renderItem={({ item }) => (
          <ShadowReviewCard
            busy={busyId === item.id}
            editedReply={editingId === item.id ? editedReply : ""}
            editing={editingId === item.id}
            onApprove={() => void decide(item, "approved")}
            onEditedReplyChange={setEditedReply}
            onReject={() => void decide(item, "rejected")}
            onStartEdit={() => startEdit(item)}
            onSubmitEdit={() => void decide(item, "edited")}
            review={item}
          />
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: C.bg, gap: 14 },
  loadingText: { color: C.text2, fontSize: 14 },
  listContent: { width: "100%", maxWidth: 760, alignSelf: "center", padding: 18, paddingBottom: 48, gap: 14 },
  headerWrap: { gap: 22, marginBottom: 2 },
  topbar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  brand: { flexDirection: "row", alignItems: "center", gap: 11 },
  brandMark: { width: 39, height: 39, borderRadius: 12, backgroundColor: C.primary, alignItems: "center", justifyContent: "center" },
  brandLetter: { color: "#fff", fontWeight: "800", fontSize: 19 },
  brandName: { color: C.text, fontSize: 14, fontWeight: "800" },
  clinicName: { color: C.text3, fontSize: 11, marginTop: 2 },
  logout: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: R.sm },
  logoutText: { color: C.text2, fontSize: 13, fontWeight: "600" },
  welcome: { flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", gap: 14 },
  welcomeCopy: { flex: 1 },
  eyebrow: { color: C.primary, fontSize: 10, fontWeight: "800", letterSpacing: 1.3, marginBottom: 7 },
  title: { color: C.text, fontSize: 25, fontWeight: "800", letterSpacing: -0.5 },
  subtitle: { color: C.text2, fontSize: 14, lineHeight: 20, marginTop: 7 },
  pendingBox: { backgroundColor: C.amberSoft, borderRadius: R.md, alignItems: "center", minWidth: 92, padding: 11 },
  pendingValue: { color: C.amber, fontSize: 24, fontWeight: "800" },
  pendingLabel: { color: C.amber, fontSize: 10, marginTop: 1 },
  sectionHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 },
  sectionTitle: { color: C.text, fontSize: 17, fontWeight: "700" },
  errorBox: { backgroundColor: C.redSoft, borderRadius: R.sm, padding: 11 },
  errorText: { color: C.red, fontSize: 12, lineHeight: 17 },
  check: { color: C.green, fontSize: 24, fontWeight: "800" },
});

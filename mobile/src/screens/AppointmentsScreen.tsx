import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import {
  api,
  type AppointmentStatus,
  type ClinicalAppointment,
  type ClinicalProcedureInput,
  type ProcedureStatus,
} from "../api";
import { useAuth } from "../auth";
import { Badge, Button, EmptyState, StatusRow } from "../components/ui";
import { C, MONO, R } from "../theme";

type Props = { status: "pending" | "confirmed" };

const PROCEDURE_STATUS: Array<{ id: ProcedureStatus; label: string }> = [
  { id: "planned", label: "Planlandı" },
  { id: "in_progress", label: "İşlemde" },
  { id: "completed", label: "Tamamlandı" },
  { id: "cancelled", label: "İptal" },
];

function dateKey(value?: string | null) {
  if (!value) return "unscheduled";
  const date = new Date(value);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function formatDay(value?: string | null) {
  if (!value) return "Tarihi belirlenmemiş";
  return new Intl.DateTimeFormat("tr-TR", { weekday: "long", day: "2-digit", month: "long" }).format(new Date(value));
}

const WEEKDAYS = ["PAZ", "PZT", "SAL", "ÇAR", "PER", "CUM", "CMT"];

function monthStart(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), 1, 12);
}

function shiftMonth(value: Date, amount: number) {
  return new Date(value.getFullYear(), value.getMonth() + amount, 1, 12);
}

function monthLabel(value: Date) {
  return new Intl.DateTimeFormat("tr-TR", { month: "long", year: "numeric" }).format(value);
}

function calendarDays(month: Date) {
  const first = monthStart(month);
  const gridStart = new Date(first);
  gridStart.setDate(first.getDate() - first.getDay());
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(gridStart);
    date.setDate(gridStart.getDate() + index);
    return date;
  });
}

function formatTime(value?: string | null) {
  if (!value) return "—:—";
  return new Intl.DateTimeFormat("tr-TR", { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function toEditorDate(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function parseEditorDate(value: string): string | null | undefined {
  if (!value.trim()) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})$/.exec(value.trim());
  if (!match) return undefined;
  const [, year, month, day, hour, minute] = match;
  const parsed = new Date(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute));
  return Number.isNaN(parsed.getTime()) ? undefined : parsed.toISOString();
}

function appointmentError(error: unknown) {
  const message = error instanceof Error ? error.message : "";
  if (message.startsWith("409")) return "Bu saat aralığında hekimin başka bir randevusu var.";
  if (message.startsWith("400")) return "Onay için önce geçerli bir tarih ve saat belirle.";
  return "Randevu bilgisi kaydedilemedi. Lütfen tekrar dene.";
}

export function AppointmentsScreen({ status }: Props) {
  const { token, user, logout } = useAuth();
  const [appointments, setAppointments] = useState<ClinicalAppointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState("");
  const [visibleMonth, setVisibleMonth] = useState(() => monthStart(new Date()));
  const [selectedAppointmentId, setSelectedAppointmentId] = useState<number | null>(null);
  const [editing, setEditing] = useState<ClinicalAppointment | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setError(null);
    try {
      setAppointments(await api.appointments(token));
    } catch (nextError) {
      setError(appointmentError(nextError));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const statusRows = useMemo(
    () => appointments.filter((appointment) => appointment.status === status),
    [appointments, status],
  );
  const dates = useMemo(
    () => Array.from(new Set(statusRows.map((item) => dateKey(item.starts_at)))).sort(),
    [statusRows],
  );
  const appointmentsByDate = useMemo(() => statusRows.reduce<Record<string, ClinicalAppointment[]>>((groups, item) => {
    const key = dateKey(item.starts_at);
    if (key !== "unscheduled") (groups[key] ||= []).push(item);
    return groups;
  }, {}), [statusRows]);

  useEffect(() => {
    if (!dates.length || selectedDate) return;
    const nextDate = dates[0];
    setSelectedDate(nextDate);
    if (nextDate !== "unscheduled") setVisibleMonth(monthStart(new Date(`${nextDate}T12:00:00`)));
  }, [dates, selectedDate]);

  const rows = useMemo(
    () => statusRows
      .filter((item) => dateKey(item.starts_at) === selectedDate)
      .sort((a, b) => (a.starts_at ? new Date(a.starts_at).getTime() : Number.MAX_SAFE_INTEGER) - (b.starts_at ? new Date(b.starts_at).getTime() : Number.MAX_SAFE_INTEGER)),
    [selectedDate, statusRows],
  );

  useEffect(() => {
    setSelectedAppointmentId((current) => rows.some((item) => item.id === current) ? current : rows[0]?.id ?? null);
  }, [rows]);

  async function changeStatus(appointment: ClinicalAppointment, nextStatus: AppointmentStatus) {
    if (!token || busyId !== null) return;
    const previous = appointments;
    setBusyId(appointment.id);
    setError(null);
    setAppointments((current) => current.map((item) => item.id === appointment.id ? { ...item, status: nextStatus } : item));
    try {
      await api.updateAppointment(appointment.id, token, nextStatus);
      await load();
    } catch (nextError) {
      setAppointments(previous);
      setError(appointmentError(nextError));
    } finally {
      setBusyId(null);
    }
  }

  async function saveClinicalDetails(
    appointment: ClinicalAppointment,
    details: {
      starts_at: string | null;
      duration_minutes: number;
      visit_reason: string | null;
      notes: string | null;
      procedures: ClinicalProcedureInput[];
    },
  ) {
    if (!token) return;
    const updated = await api.updateAppointmentDetails(appointment.id, token, details);
    setAppointments((current) => current.map((item) => item.id === updated.id ? updated : item));
    setEditing(null);
  }

  function refresh() {
    setRefreshing(true);
    void load();
  }

  return (
    <View style={styles.screen}>
      <FlatList
        contentContainerStyle={styles.content}
        data={rows}
        keyExtractor={(item) => String(item.id)}
        ListHeaderComponent={
          <View style={styles.headerWrap}>
            <View style={styles.topbar}>
              <View style={styles.brand}>
                <View style={styles.brandMark}><Text style={styles.brandLetter}>C</Text></View>
                <View><Text style={styles.brandName}>Cogni Klinik</Text><Text style={styles.doctorName}>{user?.full_name}</Text></View>
              </View>
              <Pressable onPress={() => void logout()} style={styles.logout}><Text style={styles.logoutText}>Çıkış</Text></Pressable>
            </View>

            <View>
              <Text style={styles.eyebrow}>{status === "pending" ? "RANDEVU TALEPLERİ" : "HEKİM TAKVİMİ"}</Text>
              <Text style={styles.title}>{status === "pending" ? "Bekleyen randevular" : "Onaylanan randevular"}</Text>
              <Text style={styles.subtitle}>{status === "pending" ? "Saatini ve klinik planını tamamla, ardından takvimine onayla." : "Sana özel saatli ajanda ve hastaya uygulanacak işlem planları."}</Text>
            </View>

            <MonthCalendar
              appointmentsByDate={appointmentsByDate}
              month={visibleMonth}
              onMonthChange={(amount) => {
                const target = shiftMonth(visibleMonth, amount);
                const prefix = `${target.getFullYear()}-${String(target.getMonth() + 1).padStart(2, "0")}`;
                setVisibleMonth(target);
                setSelectedDate(dates.find((date) => date.startsWith(prefix)) || dateKey(target.toISOString()));
              }}
              onSelect={(date) => setSelectedDate(date)}
              selectedDate={selectedDate}
            />

            <View style={styles.sectionHead}>
              <View><Text style={styles.sectionTitle}>{selectedDate && selectedDate !== "unscheduled" ? formatDay(`${selectedDate}T12:00:00`) : "Gün ajandası"}</Text><Text style={styles.sectionSubtitle}>{rows.length ? `${rows.length} saat planlandı` : "Bu gün için kayıt bulunmuyor"}</Text></View>
              <Badge tone={status === "pending" ? "amber" : "green"}>{status === "pending" ? "Onay bekliyor" : "Takvimde"}</Badge>
            </View>
            {error ? <Pressable onPress={refresh} style={styles.errorBox}><Text style={styles.errorText}>{error}</Text></Pressable> : null}
          </View>
        }
        ListEmptyComponent={loading ? <ActivityIndicator color={C.primary} size="large" style={styles.loader} /> : <EmptyState body={status === "pending" ? "Bu tarihte onayını bekleyen randevu yok." : "Onayladığın saatli randevular burada görünecek."} icon={<Text style={styles.emptyIcon}>{status === "pending" ? "◷" : "✓"}</Text>} title={status === "pending" ? "Bekleyen talep yok" : "Takvim boş"} />}
        refreshControl={<RefreshControl onRefresh={refresh} refreshing={refreshing} tintColor={C.primary} />}
        renderItem={({ item }) => (
          <View style={styles.agendaItem}>
            <AppointmentSlot
              appointment={item}
              busy={busyId === item.id}
              expanded={selectedAppointmentId === item.id}
              onCancel={() => void changeStatus(item, "cancelled")}
              onConfirm={() => void changeStatus(item, "confirmed")}
              onEdit={() => setEditing(item)}
              onPress={() => setSelectedAppointmentId((current) => current === item.id ? null : item.id)}
            />
          </View>
        )}
      />
      <ClinicalPlanModal appointment={editing} onClose={() => setEditing(null)} onSave={saveClinicalDetails} />
    </View>
  );
}

function MonthCalendar({ appointmentsByDate, month, onMonthChange, onSelect, selectedDate }: { appointmentsByDate: Record<string, ClinicalAppointment[]>; month: Date; onMonthChange: (amount: number) => void; onSelect: (date: string) => void; selectedDate: string }) {
  return (
    <View style={styles.calendar}>
      <View style={styles.calendarHead}>
        <Text style={styles.calendarMonth}>{monthLabel(month)}</Text>
        <View style={styles.calendarNav}><Pressable accessibilityLabel="Önceki ay" onPress={() => onMonthChange(-1)} style={styles.calendarArrow}><Text style={styles.calendarArrowText}>‹</Text></Pressable><Pressable accessibilityLabel="Sonraki ay" onPress={() => onMonthChange(1)} style={styles.calendarArrow}><Text style={styles.calendarArrowText}>›</Text></Pressable></View>
      </View>
      <View style={styles.weekRow}>{WEEKDAYS.map((day) => <Text key={day} style={styles.weekDay}>{day}</Text>)}</View>
      <View style={styles.monthGrid}>
        {calendarDays(month).map((date) => {
          const key = dateKey(date.toISOString());
          const dayAppointments = appointmentsByDate[key] || [];
          const count = dayAppointments.length;
          const firstTime = dayAppointments[0]?.starts_at ? formatTime(dayAppointments[0].starts_at) : null;
          const selected = selectedDate === key;
          const outside = date.getMonth() !== month.getMonth();
          return <Pressable accessibilityLabel={`${date.getDate()} ${monthLabel(date)}${count ? `, ${count} randevu, ilk saat ${firstTime}` : ", randevu yok"}`} key={key} onPress={() => onSelect(key)} style={[styles.dayCell, count > 0 && styles.dayCellBusy, selected && styles.dayCellSelected]}><Text style={[styles.dayNumber, outside && styles.dayNumberOutside, selected && styles.dayNumberSelected]}>{date.getDate()}</Text>{count > 0 ? <View style={[styles.dayAppointment, selected && styles.dayAppointmentSelected]}><Text style={[styles.dayAppointmentCount, selected && styles.dayAppointmentTextSelected]}>{count} rdv</Text><Text style={[styles.dayAppointmentTime, selected && styles.dayAppointmentTextSelected]}>{firstTime}</Text></View> : null}</Pressable>;
        })}
      </View>
    </View>
  );
}

function AppointmentSlot({ appointment, busy, expanded, onConfirm, onCancel, onEdit, onPress }: { appointment: ClinicalAppointment; busy: boolean; expanded: boolean; onConfirm: () => void; onCancel: () => void; onEdit: () => void; onPress: () => void }) {
  return <View style={styles.slotWrap}><Pressable onPress={onPress} style={[styles.timeSlot, expanded && styles.timeSlotActive]}><View><Text style={[styles.slotTime, expanded && styles.slotTimeActive]}>{formatTime(appointment.starts_at)} – {formatTime(appointment.ends_at)}</Text><Text style={[styles.slotPatient, expanded && styles.slotPatientActive]}>{appointment.patient_name || "İsimsiz hasta"}</Text></View><View style={styles.slotRight}><Badge tone={appointment.status === "confirmed" ? "green" : "amber"}>{appointment.status === "confirmed" ? "Onaylı" : "Bekliyor"}</Badge><Text style={[styles.slotChevron, expanded && styles.slotChevronActive]}>{expanded ? "⌃" : "⌄"}</Text></View></Pressable>{expanded ? <AppointmentCard appointment={appointment} busy={busy} onCancel={onCancel} onConfirm={onConfirm} onEdit={onEdit} /> : null}</View>;
}

function AppointmentCard({ appointment, busy, onConfirm, onCancel, onEdit }: { appointment: ClinicalAppointment; busy: boolean; onConfirm: () => void; onCancel: () => void; onEdit: () => void }) {
  const confirmed = appointment.status === "confirmed";
  const completed = appointment.procedures.filter((item) => item.status === "completed").length;
  return (
    <View style={styles.card}>
      <View style={styles.cardHead}>
        <View style={styles.timeColumn}><Text style={styles.time}>{formatTime(appointment.starts_at)}</Text><Text style={styles.endTime}>{appointment.starts_at ? `${formatTime(appointment.ends_at)} · ${appointment.duration_minutes} dk` : "Saat gerekli"}</Text></View>
        <Badge tone={confirmed ? "green" : "amber"}>{confirmed ? "Onaylandı" : "Bekliyor"}</Badge>
      </View>
      <View style={styles.patientBlock}><Text style={styles.patient}>{appointment.patient_name || "İsimsiz hasta"}</Text>{appointment.patient_phone ? <Text style={styles.phone}>{appointment.patient_phone}</Text> : null}</View>
      <View style={styles.metaRow}><Badge tone="accent">{appointment.department}</Badge>{appointment.branch_name ? <Text style={styles.meta}>{appointment.branch_name}</Text> : null}</View>
      <View style={styles.clinicalSummary}>
        <Text style={styles.summaryLabel}>ZİYARET NEDENİ</Text>
        <Text style={appointment.visit_reason ? styles.summaryText : styles.summaryEmpty}>{appointment.visit_reason || "Henüz klinik neden girilmedi"}</Text>
        <View style={styles.procedureHeader}><Text style={styles.summaryLabel}>İŞLEM PLANI</Text>{appointment.procedures.length ? <Text style={styles.procedureCount}>{completed}/{appointment.procedures.length} tamamlandı</Text> : null}</View>
        {appointment.procedures.length ? appointment.procedures.map((procedure) => <View key={procedure.id} style={styles.procedureRow}><View style={[styles.procedureDot, procedure.status === "completed" && styles.procedureDotDone, procedure.status === "in_progress" && styles.procedureDotActive]} /><View style={styles.procedureCopy}><Text style={styles.procedureName}>{procedure.name}</Text><Text style={styles.procedureMeta}>{[procedure.tooth ? `Diş ${procedure.tooth}` : null, procedure.code, PROCEDURE_STATUS.find((item) => item.id === procedure.status)?.label].filter(Boolean).join(" · ")}</Text></View></View>) : <Text style={styles.summaryEmpty}>İşlem planı henüz oluşturulmadı</Text>}
      </View>
      <Button block onPress={onEdit} variant="ghost">Klinik planı ve saati düzenle</Button>
      {confirmed ? <StatusRow tone="green">Hekim takviminde · Randevu #{appointment.id}</StatusRow> : <View style={styles.actions}><Button disabled={!appointment.starts_at} loading={busy} onPress={onConfirm} style={styles.confirm}>Onayla</Button><Button disabled={busy} onPress={onCancel} variant="danger">İptal et</Button></View>}
    </View>
  );
}

function ClinicalPlanModal({ appointment, onClose, onSave }: { appointment: ClinicalAppointment | null; onClose: () => void; onSave: (appointment: ClinicalAppointment, details: { starts_at: string | null; duration_minutes: number; visit_reason: string | null; notes: string | null; procedures: ClinicalProcedureInput[] }) => Promise<void> }) {
  const [dateTime, setDateTime] = useState("");
  const [duration, setDuration] = useState("30");
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [procedures, setProcedures] = useState<ClinicalProcedureInput[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!appointment) return;
    setDateTime(toEditorDate(appointment.starts_at));
    setDuration(String(appointment.duration_minutes || 30));
    setReason(appointment.visit_reason || "");
    setNotes(appointment.notes || "");
    setProcedures(appointment.procedures.map((item) => ({ id: item.id, name: item.name, code: item.code, tooth: item.tooth, status: item.status, notes: item.notes, sort_order: item.sort_order })));
    setError(null);
  }, [appointment]);

  if (!appointment) return null;
  const currentAppointment = appointment;

  function updateProcedure(index: number, patch: Partial<ClinicalProcedureInput>) {
    setProcedures((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
  }

  async function submit() {
    const startsAt = parseEditorDate(dateTime);
    const minutes = Number(duration);
    if (startsAt === undefined) { setError("Tarih formatı YYYY-AA-GG SS:DD olmalı."); return; }
    if (!Number.isInteger(minutes) || minutes < 15 || minutes > 240) { setError("Süre 15–240 dakika arasında olmalı."); return; }
    if (procedures.some((item) => item.name.trim().length < 2)) { setError("Her klinik işlemin adı yazılmalı."); return; }
    setSaving(true); setError(null);
    try {
      await onSave(currentAppointment, { starts_at: startsAt, duration_minutes: minutes, visit_reason: reason.trim() || null, notes: notes.trim() || null, procedures: procedures.map((item, index) => ({ ...item, name: item.name.trim(), sort_order: index })) });
    } catch (nextError) { setError(appointmentError(nextError)); } finally { setSaving(false); }
  }

  return (
    <Modal animationType="slide" onRequestClose={onClose} transparent visible>
      <View style={styles.modalBackdrop}><View style={styles.modalSheet}>
        <View style={styles.modalHead}><View><Text style={styles.modalEyebrow}>KLİNİK RANDEVU PLANI</Text><Text style={styles.modalTitle}>{appointment.patient_name || "Hasta"}</Text></View><Pressable onPress={onClose} style={styles.modalClose}><Text style={styles.modalCloseText}>×</Text></Pressable></View>
        <ScrollView contentContainerStyle={styles.modalContent} keyboardShouldPersistTaps="handled">
          <Field label="Tarih ve saat" hint="YYYY-AA-GG SS:DD"><TextInput value={dateTime} onChangeText={setDateTime} placeholder="2026-06-22 14:30" placeholderTextColor={C.text3} style={styles.input} /></Field>
          <Field label="Randevu süresi (dakika)"><TextInput value={duration} onChangeText={setDuration} keyboardType="number-pad" style={styles.input} /></Field>
          <Field label="Ziyaret nedeni"><TextInput value={reason} onChangeText={setReason} multiline placeholder="Örn. 46 numaralı dişte ağrı değerlendirmesi" placeholderTextColor={C.text3} style={[styles.input, styles.multiline]} /></Field>
          <Field label="Klinik not"><TextInput value={notes} onChangeText={setNotes} multiline placeholder="Muayene öncesi/sonrası ekip notu" placeholderTextColor={C.text3} style={[styles.input, styles.multiline]} /></Field>
          <View style={styles.procedureEditorHead}><View><Text style={styles.fieldLabel}>Uygulanacak işlemler</Text><Text style={styles.fieldHint}>Planlanan ve tamamlanan klinik adımlar</Text></View><Pressable onPress={() => setProcedures((current) => [...current, { name: "", status: "planned", sort_order: current.length }])} style={styles.addProcedure}><Text style={styles.addProcedureText}>+ İşlem</Text></Pressable></View>
          {procedures.map((procedure, index) => <View key={procedure.id ?? `new-${index}`} style={styles.procedureEditor}><TextInput value={procedure.name} onChangeText={(value) => updateProcedure(index, { name: value })} placeholder="İşlem adı" placeholderTextColor={C.text3} style={styles.input} /><View style={styles.editorRow}><TextInput value={procedure.tooth || ""} onChangeText={(value) => updateProcedure(index, { tooth: value })} placeholder="Diş no" placeholderTextColor={C.text3} style={[styles.input, styles.flexInput]} /><TextInput value={procedure.code || ""} onChangeText={(value) => updateProcedure(index, { code: value })} placeholder="İşlem kodu" placeholderTextColor={C.text3} style={[styles.input, styles.flexInput]} /></View><View style={styles.statusChips}>{PROCEDURE_STATUS.map((option) => <Pressable key={option.id} onPress={() => updateProcedure(index, { status: option.id })} style={[styles.statusChip, procedure.status === option.id && styles.statusChipActive]}><Text style={[styles.statusChipText, procedure.status === option.id && styles.statusChipTextActive]}>{option.label}</Text></Pressable>)}</View></View>)}
          {error ? <Text style={styles.modalError}>{error}</Text> : null}
          <Button block loading={saving} onPress={() => void submit()}>Klinik planı kaydet</Button>
        </ScrollView>
      </View></View>
    </Modal>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return <View style={styles.field}><Text style={styles.fieldLabel}>{label}</Text>{hint ? <Text style={styles.fieldHint}>{hint}</Text> : null}{children}</View>;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg }, content: { width: "100%", maxWidth: 760, alignSelf: "center", padding: 14, paddingBottom: 36, gap: 10 }, headerWrap: { gap: 14, marginBottom: 2 }, topbar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, brand: { flexDirection: "row", alignItems: "center", gap: 9 }, brandMark: { width: 34, height: 34, borderRadius: 10, backgroundColor: C.primary, alignItems: "center", justifyContent: "center" }, brandLetter: { color: "#fff", fontWeight: "800", fontSize: 17 }, brandName: { color: C.text, fontSize: 13, fontWeight: "800" }, doctorName: { color: C.text3, fontSize: 10, marginTop: 1 }, logout: { paddingHorizontal: 10, paddingVertical: 7, borderRadius: R.sm }, logoutText: { color: C.text2, fontSize: 12, fontWeight: "600" }, eyebrow: { color: C.primary, fontSize: 9, fontWeight: "800", letterSpacing: 1.2, marginBottom: 5 }, title: { color: C.text, fontSize: 22, fontWeight: "800", letterSpacing: -0.4 }, subtitle: { color: C.text2, fontSize: 12, lineHeight: 17, marginTop: 5 },
  calendar: { backgroundColor: C.surface, borderColor: C.border, borderWidth: 1, borderRadius: R.md, padding: 10, gap: 8 }, calendarHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderBottomColor: C.border, borderBottomWidth: 1, paddingBottom: 8 }, calendarMonth: { color: C.text, fontSize: 16, fontWeight: "800", textTransform: "capitalize" }, calendarNav: { flexDirection: "row", gap: 4 }, calendarArrow: { width: 30, height: 30, borderRadius: 8, backgroundColor: C.surfaceAlt, alignItems: "center", justifyContent: "center" }, calendarArrowText: { color: C.text2, fontSize: 23, lineHeight: 25 }, weekRow: { flexDirection: "row", borderBottomColor: C.border, borderBottomWidth: 1, paddingBottom: 7 }, weekDay: { width: "14.285%", color: C.text3, textAlign: "center", fontSize: 8, fontWeight: "800", letterSpacing: 0.4 }, monthGrid: { flexDirection: "row", flexWrap: "wrap", rowGap: 3 }, dayCell: { width: "14.285%", height: 46, borderRadius: 8, alignItems: "center", justifyContent: "center", gap: 1, paddingHorizontal: 1 }, dayCellBusy: { backgroundColor: C.primarySoft }, dayCellSelected: { backgroundColor: C.primary }, dayNumber: { color: C.text2, fontSize: 11, fontWeight: "700" }, dayNumberOutside: { color: C.text3, opacity: 0.42 }, dayNumberSelected: { color: "#fff", fontWeight: "800" }, dayAppointment: { minWidth: 31, backgroundColor: C.surface, borderRadius: 4, paddingHorizontal: 2, paddingVertical: 1, alignItems: "center" }, dayAppointmentSelected: { backgroundColor: "rgba(255,255,255,0.18)" }, dayAppointmentCount: { color: C.primaryDark, fontSize: 6.5, lineHeight: 7, fontWeight: "800" }, dayAppointmentTime: { color: C.primaryDark, fontFamily: MONO, fontSize: 6.5, lineHeight: 7, fontWeight: "700" }, dayAppointmentTextSelected: { color: "#fff" }, sectionHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 }, sectionTitle: { color: C.text, fontSize: 15, fontWeight: "800", textTransform: "capitalize" }, sectionSubtitle: { color: C.text3, fontSize: 10, marginTop: 2 }, agendaItem: { gap: 7 }, slotWrap: { gap: 7 }, timeSlot: { minHeight: 58, backgroundColor: C.surface, borderColor: C.borderStrong, borderWidth: 1, borderRadius: R.md, paddingHorizontal: 12, paddingVertical: 9, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 }, timeSlotActive: { backgroundColor: C.primaryDark, borderColor: C.primaryDark }, slotTime: { color: C.text, fontFamily: MONO, fontSize: 14, fontWeight: "800" }, slotTimeActive: { color: "#fff" }, slotPatient: { color: C.text2, fontSize: 11, marginTop: 2 }, slotPatientActive: { color: "rgba(255,255,255,0.72)" }, slotRight: { flexDirection: "row", alignItems: "center", gap: 6 }, slotChevron: { color: C.text3, fontSize: 15 }, slotChevronActive: { color: "#fff" },
  card: { backgroundColor: C.surface, borderColor: C.border, borderRadius: R.lg, borderWidth: 1, padding: 16, gap: 13 }, cardHead: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }, timeColumn: { gap: 2 }, time: { color: C.text, fontFamily: MONO, fontSize: 25, fontWeight: "800" }, endTime: { color: C.text3, fontSize: 11 }, patientBlock: { gap: 3 }, patient: { color: C.text, fontSize: 17, fontWeight: "700" }, phone: { color: C.text2, fontSize: 13 }, metaRow: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 8 }, meta: { color: C.text2, fontSize: 12 }, clinicalSummary: { backgroundColor: C.surfaceAlt, borderRadius: R.sm, padding: 12, gap: 8 }, summaryLabel: { color: C.text3, fontFamily: MONO, fontSize: 9, letterSpacing: 0.7 }, summaryText: { color: C.text, fontSize: 13, lineHeight: 19 }, summaryEmpty: { color: C.text3, fontSize: 12, fontStyle: "italic" }, procedureHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 3 }, procedureCount: { color: C.green, fontSize: 10, fontWeight: "700" }, procedureRow: { flexDirection: "row", alignItems: "center", gap: 9 }, procedureDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: C.amber }, procedureDotDone: { backgroundColor: C.green }, procedureDotActive: { backgroundColor: C.primary }, procedureCopy: { flex: 1 }, procedureName: { color: C.text, fontSize: 13, fontWeight: "600" }, procedureMeta: { color: C.text3, fontSize: 10, marginTop: 2 }, actions: { flexDirection: "row", gap: 8 }, confirm: { flex: 1 }, loader: { marginTop: 60 }, emptyIcon: { color: C.green, fontSize: 24, fontWeight: "800" }, errorBox: { backgroundColor: C.redSoft, borderRadius: R.sm, padding: 11 }, errorText: { color: C.red, fontSize: 12 },
  modalBackdrop: { flex: 1, backgroundColor: "rgba(15,31,27,0.38)", justifyContent: "flex-end" }, modalSheet: { backgroundColor: C.bg, borderTopLeftRadius: R.xl, borderTopRightRadius: R.xl, maxHeight: "92%", overflow: "hidden" }, modalHead: { backgroundColor: C.surface, borderBottomColor: C.border, borderBottomWidth: 1, flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 18 }, modalEyebrow: { color: C.primary, fontSize: 9, fontWeight: "800", letterSpacing: 1.1 }, modalTitle: { color: C.text, fontSize: 20, fontWeight: "800", marginTop: 3 }, modalClose: { width: 36, height: 36, borderRadius: 18, backgroundColor: C.surfaceAlt, alignItems: "center", justifyContent: "center" }, modalCloseText: { color: C.text2, fontSize: 24, lineHeight: 26 }, modalContent: { padding: 18, gap: 17, paddingBottom: 36 }, field: { gap: 7 }, fieldLabel: { color: C.text, fontSize: 12, fontWeight: "700" }, fieldHint: { color: C.text3, fontSize: 10 }, input: { backgroundColor: C.surface, borderColor: C.border, borderWidth: 1, borderRadius: R.sm, color: C.text, fontSize: 14, minHeight: 46, paddingHorizontal: 12, paddingVertical: 10 }, multiline: { minHeight: 74, textAlignVertical: "top" }, procedureEditorHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, addProcedure: { backgroundColor: C.primarySoft, borderRadius: R.sm, paddingHorizontal: 12, paddingVertical: 8 }, addProcedureText: { color: C.primary, fontSize: 12, fontWeight: "800" }, procedureEditor: { backgroundColor: C.surfaceAlt, borderColor: C.border, borderWidth: 1, borderRadius: R.md, padding: 11, gap: 9 }, editorRow: { flexDirection: "row", gap: 8 }, flexInput: { flex: 1 }, statusChips: { flexDirection: "row", flexWrap: "wrap", gap: 6 }, statusChip: { backgroundColor: C.surface, borderColor: C.border, borderWidth: 1, borderRadius: 8, paddingHorizontal: 9, paddingVertical: 6 }, statusChipActive: { backgroundColor: C.primarySoft, borderColor: C.primary }, statusChipText: { color: C.text2, fontSize: 10, fontWeight: "700" }, statusChipTextActive: { color: C.primary }, modalError: { color: C.red, fontSize: 12, lineHeight: 17 },
});

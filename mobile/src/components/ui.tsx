import type { PropsWithChildren, ReactNode } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from "react-native";

import { C, MONO, R } from "../theme";

export type Tone = "neutral" | "accent" | "green" | "amber" | "red" | "purple";
export type ButtonVariant = "primary" | "ghost" | "danger";

const toneColors: Record<Tone, { background: string; color: string; border: string }> = {
  neutral: { background: C.surfaceAlt, color: C.text2, border: C.border },
  accent: { background: C.primarySoft, color: C.primary, border: "transparent" },
  green: { background: C.greenSoft, color: C.green, border: "transparent" },
  amber: { background: C.amberSoft, color: C.amber, border: "transparent" },
  red: { background: C.redSoft, color: C.red, border: "transparent" },
  purple: { background: C.purpleSoft, color: C.purple, border: "transparent" },
};

export function Badge({ children, tone = "neutral" }: PropsWithChildren<{ tone?: Tone }>) {
  const palette = toneColors[tone];
  return (
    <View style={[styles.badge, { backgroundColor: palette.background, borderColor: palette.border }]}>
      <Text style={[styles.badgeText, { color: palette.color }]}>{children}</Text>
    </View>
  );
}

type ButtonProps = PropsWithChildren<{
  variant?: ButtonVariant;
  disabled?: boolean;
  loading?: boolean;
  onPress: () => void;
  block?: boolean;
  style?: StyleProp<ViewStyle>;
}>;

export function Button({
  children,
  variant = "primary",
  disabled = false,
  loading = false,
  onPress,
  block = false,
  style,
}: ButtonProps) {
  const palette = buttonColors[variant];
  const inactive = disabled || loading;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: inactive, busy: loading }}
      disabled={inactive}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: palette.background, borderColor: palette.border },
        block && styles.buttonBlock,
        pressed && !inactive && styles.buttonPressed,
        inactive && styles.buttonDisabled,
        style,
      ]}
    >
      {loading ? <ActivityIndicator size="small" color={palette.color} /> : null}
      <Text style={[styles.buttonText, { color: palette.color }]}>{children}</Text>
    </Pressable>
  );
}

const buttonColors: Record<ButtonVariant, { background: string; color: string; border: string }> = {
  primary: { background: C.primary, color: "#ffffff", border: C.primary },
  ghost: { background: C.surfaceAlt, color: C.text, border: C.borderStrong },
  danger: { background: C.redSoft, color: C.red, border: "rgba(181,48,47,0.20)" },
};

export function Meter({ value, tone }: { value: number; tone?: "green" | "amber" | "red" }) {
  const bounded = Math.max(0, Math.min(100, value));
  const resolvedTone = tone ?? (bounded >= 80 ? "green" : bounded >= 60 ? "amber" : "red");
  return (
    <View
      accessibilityRole="progressbar"
      accessibilityValue={{ min: 0, max: 100, now: bounded }}
      style={styles.meter}
    >
      <View style={[styles.meterFill, { width: `${bounded}%`, backgroundColor: C[resolvedTone] }]} />
    </View>
  );
}

export function Dot({ tone = "neutral" }: { tone?: Exclude<Tone, "purple"> }) {
  const color = tone === "neutral" ? C.text3 : toneColors[tone].color;
  return <View style={[styles.dot, { backgroundColor: color }]} />;
}

export function StatusRow({
  children,
  tone = "neutral",
}: PropsWithChildren<{ tone?: Exclude<Tone, "purple"> }>) {
  return (
    <View style={styles.statusRow}>
      <Dot tone={tone} />
      <Text style={styles.statusText}>{children}</Text>
    </View>
  );
}

export function EmptyState({ icon, title, body }: { icon: ReactNode; title: string; body: string }) {
  return (
    <View style={styles.empty}>
      <View style={styles.emptyIcon}>{icon}</View>
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptyBody}>{body}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignSelf: "flex-start",
    borderRadius: 7,
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  badgeText: {
    fontFamily: MONO,
    fontSize: 10,
    fontWeight: "600",
    letterSpacing: 0.55,
    textTransform: "uppercase",
  },
  button: {
    minHeight: 42,
    borderRadius: R.sm,
    borderWidth: 1,
    paddingHorizontal: 15,
    paddingVertical: 10,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 7,
  },
  buttonBlock: { width: "100%" },
  buttonPressed: { opacity: 0.82, transform: [{ scale: 0.985 }] },
  buttonDisabled: { opacity: 0.48 },
  buttonText: { fontSize: 14, fontWeight: "700" },
  meter: {
    flex: 1,
    minWidth: 72,
    height: 7,
    borderRadius: 99,
    backgroundColor: C.border,
    overflow: "hidden",
  },
  meterFill: { height: "100%", borderRadius: 99 },
  dot: { width: 8, height: 8, borderRadius: 99 },
  statusRow: { flexDirection: "row", alignItems: "center", gap: 7 },
  statusText: { color: C.text2, fontSize: 12 },
  empty: {
    alignItems: "center",
    paddingHorizontal: 30,
    paddingVertical: 64,
  },
  emptyIcon: {
    width: 54,
    height: 54,
    borderRadius: 27,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: C.greenSoft,
    marginBottom: 16,
  },
  emptyTitle: { color: C.text, fontSize: 18, fontWeight: "700", marginBottom: 7 },
  emptyBody: { color: C.text2, fontSize: 14, lineHeight: 21, textAlign: "center" },
});

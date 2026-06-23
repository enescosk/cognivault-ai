import { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { useAuth } from "../auth";
import { Button, StatusRow } from "../components/ui";
import { C, R } from "../theme";

const DEMO_EMAIL = "hekim@cognivault.com";
const DEMO_PASSWORD = "demo123";

export function LoginScreen() {
  const { login } = useAuth();
  const [email, setEmail] = useState(DEMO_EMAIL);
  const [password, setPassword] = useState(DEMO_PASSWORD);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!email.trim() || !password) return;
    setSubmitting(true);
    setError(null);
    try {
      await login(email.trim(), password);
    } catch {
      setError("Giriş yapılamadı. Bilgileri ve backend bağlantısını kontrol et.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={styles.screen}
    >
      <View style={styles.content}>
        <View style={styles.brandMark}>
          <Text style={styles.brandLetter}>C</Text>
        </View>
        <Text style={styles.eyebrow}>COGNI KLINIK</Text>
          <Text style={styles.title}>Kişisel hekim alanı</Text>
        <Text style={styles.subtitle}>
          Yalnızca sana atanmış AI taslaklarını, risk sinyallerini ve KVKK veri akışını incele.
        </Text>

        <View style={styles.card}>
          <View style={styles.field}>
            <Text style={styles.label}>E-posta</Text>
            <TextInput
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
              onChangeText={setEmail}
              placeholder="hekim@klinik.com"
              placeholderTextColor={C.text3}
              style={styles.input}
              value={email}
            />
          </View>
          <View style={styles.field}>
            <Text style={styles.label}>Şifre</Text>
            <TextInput
              autoCapitalize="none"
              autoComplete="password"
              onChangeText={setPassword}
              onSubmitEditing={submit}
              placeholder="••••••••"
              placeholderTextColor={C.text3}
              secureTextEntry
              style={styles.input}
              value={password}
            />
          </View>
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <Button
            block
            disabled={!email.trim() || !password}
            loading={submitting}
            onPress={submit}
          >
            Güvenli giriş
          </Button>
          <StatusRow tone="green">Yerel-first veri işleme aktif</StatusRow>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg, justifyContent: "center" },
  content: { width: "100%", maxWidth: 460, alignSelf: "center", padding: 24 },
  brandMark: {
    width: 48,
    height: 48,
    borderRadius: 15,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: C.primary,
    marginBottom: 22,
  },
  brandLetter: { color: "#fff", fontSize: 24, fontWeight: "800" },
  eyebrow: { color: C.primary, fontSize: 11, fontWeight: "800", letterSpacing: 1.8, marginBottom: 8 },
  title: { color: C.text, fontSize: 30, fontWeight: "800", letterSpacing: -0.8, marginBottom: 10 },
  subtitle: { color: C.text2, fontSize: 15, lineHeight: 23, marginBottom: 26 },
  card: {
    backgroundColor: C.surface,
    borderColor: C.border,
    borderRadius: R.xl,
    borderWidth: 1,
    gap: 18,
    padding: 20,
  },
  field: { gap: 7 },
  label: { color: C.text2, fontSize: 12, fontWeight: "700" },
  input: {
    backgroundColor: C.surfaceAlt,
    borderColor: C.border,
    borderRadius: R.sm,
    borderWidth: 1,
    color: C.text,
    fontSize: 15,
    minHeight: 49,
    paddingHorizontal: 14,
  },
  error: { color: C.red, fontSize: 13, lineHeight: 18 },
});

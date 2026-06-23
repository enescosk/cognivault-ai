import { Pressable, StyleSheet, Text, View } from "react-native";

import { C } from "../theme";

export type AppTab = "appointments" | "confirmed" | "decisions";

const TABS: Array<{ id: AppTab; label: string; icon: string }> = [
  { id: "appointments", label: "Randevular", icon: "◷" },
  { id: "confirmed", label: "Onaylanan", icon: "✓" },
  { id: "decisions", label: "AI Kararlar", icon: "◇" },
];

export function AppTabs({ active, onChange }: { active: AppTab; onChange: (tab: AppTab) => void }) {
  return (
    <View accessibilityRole="tablist" style={styles.bar}>
      {TABS.map((tab) => {
        const selected = tab.id === active;
        return (
          <Pressable
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            key={tab.id}
            onPress={() => onChange(tab.id)}
            style={({ pressed }) => [styles.tab, pressed && styles.pressed]}
          >
            <Text style={[styles.icon, selected && styles.activeText]}>{tab.icon}</Text>
            <Text style={[styles.label, selected && styles.activeText]}>{tab.label}</Text>
            {selected ? <View style={styles.indicator} /> : null}
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    backgroundColor: C.surface,
    borderTopColor: C.border,
    borderTopWidth: 1,
    flexDirection: "row",
    paddingBottom: 7,
    paddingHorizontal: 8,
    shadowColor: "#173d36",
    shadowOffset: { width: 0, height: -4 },
    shadowOpacity: 0.05,
    shadowRadius: 10,
  },
  tab: { flex: 1, minHeight: 59, alignItems: "center", justifyContent: "center", gap: 3 },
  pressed: { opacity: 0.65 },
  icon: { color: C.text3, fontSize: 19, fontWeight: "700" },
  label: { color: C.text3, fontSize: 10, fontWeight: "700" },
  activeText: { color: C.primary },
  indicator: { position: "absolute", top: 0, width: 30, height: 3, borderRadius: 2, backgroundColor: C.primary },
});

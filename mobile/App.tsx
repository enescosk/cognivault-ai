import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { AuthProvider, useAuth } from './src/auth';
import { AppTabs, type AppTab } from './src/components/AppTabs';
import { AppointmentsScreen } from './src/screens/AppointmentsScreen';
import { LoginScreen } from './src/screens/LoginScreen';
import { QueueScreen } from './src/screens/QueueScreen';
import { C } from './src/theme';

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

function AppContent() {
  const { loading, token } = useAuth();

  return (
    <View style={styles.container}>
      {loading ? <ActivityIndicator color={C.primary} size="large" /> : token ? <AuthenticatedApp /> : <LoginScreen />}
      <StatusBar style="dark" />
    </View>
  );
}

function AuthenticatedApp() {
  const [activeTab, setActiveTab] = useState<AppTab>('appointments');

  return (
    <View style={styles.container}>
      {activeTab === 'appointments' ? <AppointmentsScreen status="pending" /> : null}
      {activeTab === 'confirmed' ? <AppointmentsScreen status="confirmed" /> : null}
      {activeTab === 'decisions' ? <QueueScreen /> : null}
      <AppTabs active={activeTab} onChange={setActiveTab} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: C.bg,
  },
});

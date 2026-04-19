import { Dashboard } from "./components/Dashboard";
import { LoginScreen } from "./components/LoginScreen";
import { AuthProvider, useAuth } from "./context/AuthContext";

function AppBody() {
  const { user, loading, login, register } = useAuth();

  if (loading) {
    return <div className="loading-shell">Preparing secure workspace...</div>;
  }

  if (!user) {
    return <LoginScreen onLogin={login} onRegister={register} />;
  }

  return <Dashboard />;
}

export default function App() {
  return (
    <AuthProvider>
      <AppBody />
    </AuthProvider>
  );
}

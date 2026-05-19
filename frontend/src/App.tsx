import { Dashboard } from "./components/Dashboard";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { LoginScreen } from "./components/LoginScreen";
import { ToastContainer } from "./components/ui/Toast";
import { AuthProvider, useAuth } from "./context/AuthContext";

function AppBody() {
  const { user, loading, login, register } = useAuth();

  if (loading) {
    return <div className="loading-shell">Preparing secure workspace...</div>;
  }

  if (!user) {
    return <LoginScreen onLogin={login} onRegister={register} />;
  }

  return (
    <ErrorBoundary scope="Workspace">
      <Dashboard />
    </ErrorBoundary>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppBody />
      <ToastContainer />
    </AuthProvider>
  );
}

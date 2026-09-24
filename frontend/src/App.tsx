import { ServerCrash } from "lucide-react";
import { Navigate, Route, Routes } from "react-router-dom";
import Header from "./components/Header";
import Logo from "./components/Logo";
import { Button, Spinner } from "./components/ui";
import { getDemo } from "./lib/demo";
import { useMeta } from "./lib/meta";
import Admin from "./pages/Admin";
import Chat from "./pages/Chat";
import NotFound from "./pages/NotFound";
import Welcome from "./pages/Welcome";

function Splash() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
      <Logo size={48} />
      <div className="flex items-center gap-2 text-sm text-muted">
        <Spinner className="text-brand" /> Waking up the demo server…
      </div>
      <p className="max-w-xs text-xs text-subtle">
        The backend scales to zero when idle, so the first request can take a few seconds.
      </p>
    </div>
  );
}

function Offline() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
      <ServerCrash size={40} className="text-bad" />
      <div>
        <h1 className="text-lg font-semibold">The demo backend isn't responding</h1>
        <p className="mt-1 text-sm text-muted">It may be redeploying. Please try again in a minute.</p>
      </div>
      <Button variant="primary" onClick={() => window.location.reload()}>
        Retry
      </Button>
    </div>
  );
}

/** In demo mode, visitors need a sandbox before they can chat. */
function RequireSession({ children }: { children: JSX.Element }) {
  const { meta } = useMeta();
  if (meta?.auth_mode === "demo" && !getDemo()) return <Navigate to="/" replace />;
  return children;
}

/** Evaluated per render (not once in App) so resetting the sandbox lands here. */
function Home() {
  const { meta } = useMeta();
  return meta?.auth_mode === "demo" && !getDemo() ? <Welcome /> : <Navigate to="/chat" replace />;
}

export default function App() {
  const { meta, loading, error } = useMeta();
  if (loading) return <Splash />;
  if (error || !meta) return <Offline />;

  return (
    <div className="flex h-full flex-col">
      <Header />
      <main className="min-h-0 flex-1">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route
            path="/chat"
            element={
              <RequireSession>
                <Chat />
              </RequireSession>
            }
          />
          <Route
            path="/console"
            element={
              <RequireSession>
                <Admin />
              </RequireSession>
            }
          />
          <Route path="/admin" element={<Navigate to="/console" replace />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  );
}

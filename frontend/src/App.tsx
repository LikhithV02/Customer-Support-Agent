import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import Admin from "./pages/Admin";
import Chat from "./pages/Chat";

function NavTab({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
          isActive
            ? "bg-indigo-500/20 text-indigo-300"
            : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
        }`
      }
    >
      {label}
    </NavLink>
  );
}

export default function App() {
  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-slate-800 bg-slate-900/60 px-6 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500 font-bold text-white">
            A
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-100">ACME Refund Support</div>
            <div className="text-xs text-slate-500">AI Customer Support Agent</div>
          </div>
        </div>
        <nav className="flex items-center gap-1">
          <NavTab to="/chat" label="Customer Chat" />
          <NavTab to="/admin" label="Admin Dashboard" />
        </nav>
      </header>
      <main className="min-h-0 flex-1">
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/admin" element={<Admin />} />
        </Routes>
      </main>
    </div>
  );
}

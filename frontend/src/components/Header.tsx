import clsx from "clsx";
import { BookOpen, Github, Moon, RotateCcw, Sun } from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";
import { LANDING_URL, REPO_URL } from "../config";
import { clearDemo, getDemo } from "../lib/demo";
import { useMeta } from "../lib/meta";
import { useTheme } from "../theme";
import DevIdentity from "./DevIdentity";
import Logo from "./Logo";
import { Badge, IconButton } from "./ui";

function Tab({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        clsx(
          "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
          isActive ? "bg-brand/10 text-brand" : "text-muted hover:bg-surface-2 hover:text-fg",
        )
      }
    >
      {label}
    </NavLink>
  );
}

export default function Header() {
  const { meta } = useMeta();
  const [theme, toggleTheme] = useTheme();
  const navigate = useNavigate();
  const demo = meta?.auth_mode === "demo" ? getDemo() : null;

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/80 backdrop-blur">
      <div className="flex h-14 items-center gap-3 px-3 sm:px-5">
        <a href={LANDING_URL} className="flex items-center gap-2.5" title="About this project">
          <Logo size={30} />
          <div className="hidden leading-tight sm:block">
            <div className="text-sm font-semibold">ACME Support</div>
            <div className="text-[11px] text-subtle">AI refund agent</div>
          </div>
        </a>

        <nav className="ml-2 flex items-center gap-1 sm:ml-4">
          <Tab to="/chat" label="Chat" />
          <Tab to="/console" label="Agent console" />
        </nav>

        <div className="ml-auto flex items-center gap-1.5">
          {meta?.auth_mode === "dev" && <DevIdentity />}
          {meta && (
            <Badge tone={meta.model === "scripted" ? "neutral" : "brand"} className="hidden md:inline-flex">
              {meta.model === "scripted" ? "Scripted model" : `Model: ${meta.model}`}
            </Badge>
          )}
          {demo && (
            <button
              onClick={() => {
                clearDemo();
                navigate("/");
              }}
              className="hidden items-center gap-1.5 rounded-full border border-warn/30 bg-warn/10 px-2.5 py-1 text-[11px] font-semibold text-warn transition-colors hover:bg-warn/20 sm:inline-flex"
              title="Discard this sandbox and start a new one"
            >
              Sandbox · reset <RotateCcw size={12} />
            </button>
          )}
          <IconButton label="About this project" onClick={() => window.open(LANDING_URL, "_blank")}>
            <BookOpen size={16} />
          </IconButton>
          <IconButton label="Source on GitHub" onClick={() => window.open(REPO_URL, "_blank")}>
            <Github size={16} />
          </IconButton>
          <IconButton
            label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            onClick={toggleTheme}
          >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </IconButton>
        </div>
      </div>
    </header>
  );
}

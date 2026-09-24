import { useEffect, useState } from "react";
import { devCustomers, devLogin, getToken, onTokenChange, setToken } from "../auth";

type Customer = { id: string; name: string; email: string };

/**
 * Local-dev identity switcher. Only renders when the backend runs with
 * AUTH_MODE=dev (the /api/dev/* routes 404 in production, so this hides itself).
 */
export default function DevIdentity() {
  const [customers, setCustomers] = useState<Customer[] | null>(null);
  const [current, setCurrent] = useState<string>("");
  const [, force] = useState(0);

  useEffect(() => {
    devCustomers().then(setCustomers);
    return onTokenChange(() => force((n) => n + 1));
  }, []);

  if (!customers) return null;

  const hasAdmin = Boolean(getToken("admin"));

  return (
    <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-xs text-amber-200">
      <span className="font-semibold">DEV</span>
      <select
        value={current}
        onChange={async (e) => {
          const id = e.target.value;
          setCurrent(id);
          if (id) await devLogin("customer", id);
          else setToken("customer", null);
        }}
        className="rounded bg-slate-900 px-1 py-0.5 text-slate-200"
        aria-label="Act as customer"
      >
        <option value="">Act as customer…</option>
        {customers.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name} ({c.id})
          </option>
        ))}
      </select>
      <button
        onClick={() => (hasAdmin ? setToken("admin", null) : devLogin("admin"))}
        className="rounded bg-slate-900 px-2 py-0.5 text-slate-200 hover:bg-slate-800"
      >
        {hasAdmin ? "Admin: on" : "Admin: off"}
      </button>
    </div>
  );
}

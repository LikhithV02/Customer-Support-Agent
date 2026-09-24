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
    <div className="flex items-center gap-2 rounded-lg border border-warn/30 bg-warn/10 px-2 py-1 text-xs text-warn">
      <span className="font-semibold">DEV</span>
      <select
        value={current}
        onChange={async (e) => {
          const id = e.target.value;
          setCurrent(id);
          if (id) await devLogin("customer", id);
          else setToken("customer", null);
        }}
        className="max-w-[10rem] rounded bg-surface px-1 py-0.5 text-fg"
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
        className="rounded bg-surface px-2 py-0.5 text-fg hover:bg-surface-2"
      >
        {hasAdmin ? "Admin: on" : "Admin: off"}
      </button>
    </div>
  );
}

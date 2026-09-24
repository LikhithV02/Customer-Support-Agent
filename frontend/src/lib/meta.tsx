import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { fetchMeta } from "../api";
import type { Meta } from "../types";

type State = { meta: Meta | null; error: boolean; loading: boolean };

const Ctx = createContext<State>({ meta: null, error: false, loading: true });

export const useMeta = () => useContext(Ctx);

/** Loads /api/meta once: tells the UI which sign-in flow the backend runs. */
export function MetaProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ meta: null, error: false, loading: true });
  useEffect(() => {
    let cancelled = false;
    const load = async (attempt: number) => {
      try {
        const meta = await fetchMeta();
        if (!cancelled) setState({ meta, error: false, loading: false });
      } catch {
        // Serverless backends can take a few seconds to cold-start.
        if (cancelled) return;
        if (attempt < 4) setTimeout(() => load(attempt + 1), 1500 * (attempt + 1));
        else setState({ meta: null, error: true, loading: false });
      }
    };
    load(0);
    return () => {
      cancelled = true;
    };
  }, []);
  return <Ctx.Provider value={state}>{children}</Ctx.Provider>;
}

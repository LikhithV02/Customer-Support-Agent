import { Edge, type Node } from "./Architecture";

/**
 * Where each piece of the public demo runs. Shares the arrow marker and edge
 * style of the request-path diagram (Architecture), which is on the same page.
 */

const H = 64;
const NODES: Node[] = [
  { id: "user", x: 10, y: 186, w: 150, title: "Visitor", sub: "browser" },
  { id: "cf", x: 230, y: 60, w: 200, title: "Cloudflare", sub: "chat UI + console, edge" },
  { id: "pages", x: 230, y: 292, w: 200, title: "GitHub Pages", sub: "this page" },
  { id: "run", x: 480, y: 186, w: 190, title: "Cloud Run", sub: "FastAPI · Singapore · 0→3", accent: true },
  { id: "omni", x: 740, y: 10, w: 200, title: "GPT-5.6 Sol", sub: "OmniRoute on own VPS" },
  { id: "gemini", x: 740, y: 98, w: 200, title: "Gemini 3.8 Flash", sub: "fallback · circuit breaker" },
  { id: "neon", x: 740, y: 186, w: 200, title: "Neon Postgres", sub: "orders · refund ledger" },
  { id: "redis", x: 740, y: 274, w: 200, title: "Upstash Redis", sub: "limits · locks · pub/sub" },
  { id: "opik", x: 740, y: 362, w: 200, title: "Opik", sub: "traces · cost · experiments" },
  { id: "gha", x: 230, y: 400, w: 200, title: "GitHub Actions", sub: "tests · evals · OIDC deploys" },
];

const at = (id: string, side: "l" | "r" | "t" | "b"): [number, number] => {
  const n = NODES.find((x) => x.id === id)!;
  return {
    l: [n.x, n.y + H / 2],
    r: [n.x + n.w, n.y + H / 2],
    t: [n.x + n.w / 2, n.y],
    b: [n.x + n.w / 2, n.y + H],
  }[side] as [number, number];
};

export default function Deployment() {
  return (
    <svg
      viewBox="0 0 950 474"
      className="h-auto w-full"
      role="img"
      aria-label="Deployment: the visitor loads the UI from Cloudflare and talks to the FastAPI backend on Cloud Run in Singapore. The backend calls GPT-5.6 through OmniRoute on a self-hosted VPS, failing over to Gemini, and uses Neon Postgres, Upstash Redis and Opik. GitHub Actions tests and deploys everything."
    >
      <Edge from={at("user", "r")} to={at("cf", "l")} />
      <Edge from={at("user", "r")} to={at("pages", "l")} />
      <Edge from={at("user", "r")} to={at("run", "l")} label="HTTPS + SSE" />
      <Edge from={at("run", "r")} to={at("omni", "l")} label="primary" />
      <Edge from={at("run", "r")} to={at("gemini", "l")} />
      <Edge from={at("run", "r")} to={at("neon", "l")} />
      <Edge from={at("run", "r")} to={at("redis", "l")} />
      <Edge from={at("run", "r")} to={at("opik", "l")} />
      <Edge from={at("gha", "r")} to={at("run", "b")} />
      {NODES.map((n) => (
        <g key={n.id}>
          <rect
            x={n.x}
            y={n.y}
            width={n.w}
            height={H}
            rx={12}
            className={n.accent ? "fill-surface stroke-brand" : "fill-surface stroke-line"}
            strokeWidth={n.accent ? 2 : 1.5}
          />
          <text x={n.x + 16} y={n.y + 27} className="fill-fg" fontSize={15} fontWeight={600}>
            {n.title}
          </text>
          <text x={n.x + 16} y={n.y + 47} className="fill-subtle" fontSize={12}>
            {n.sub}
          </text>
        </g>
      ))}
    </svg>
  );
}

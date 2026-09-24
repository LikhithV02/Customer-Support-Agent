/**
 * Architecture diagram. Inline SVG so it inherits the page's theme tokens;
 * dashed edges animate to show which way requests and events flow.
 */
type Node = { id: string; x: number; y: number; w: number; title: string; sub: string; accent?: boolean };

const H = 64;
const NODES: Node[] = [
  { id: "ui", x: 10, y: 168, w: 170, title: "Chat UI + console", sub: "React · Vercel" },
  { id: "api", x: 240, y: 168, w: 170, title: "FastAPI", sub: "JWT · SSE · Cloud Run", accent: true },
  { id: "agent", x: 480, y: 70, w: 190, title: "LangGraph agent", sub: "ReAct tool loop" },
  { id: "llm", x: 740, y: 20, w: 200, title: "Claude", sub: "budget-capped → scripted" },
  { id: "tools", x: 480, y: 188, w: 190, title: "Tools + policy engine", sub: "deterministic gate", accent: true },
  { id: "pg", x: 740, y: 188, w: 200, title: "Postgres", sub: "row locks · unique index" },
  { id: "redis", x: 480, y: 310, w: 190, title: "Redis", sub: "limits · locks · pub/sub" },
];

const center = (id: string, side: "l" | "r" | "t" | "b") => {
  const n = NODES.find((x) => x.id === id)!;
  return {
    l: [n.x, n.y + H / 2],
    r: [n.x + n.w, n.y + H / 2],
    t: [n.x + n.w / 2, n.y],
    b: [n.x + n.w / 2, n.y + H],
  }[side] as [number, number];
};

function Edge({
  from,
  to,
  label,
}: {
  from: [number, number];
  to: [number, number];
  label?: string;
}) {
  const [x1, y1] = from;
  const [x2, y2] = to;
  const mx = (x1 + x2) / 2;
  const d = `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`;
  return (
    <g>
      <path d={d} fill="none" className="stroke-line" strokeWidth={2} />
      <path d={d} fill="none" className="flow stroke-brand" strokeWidth={2} markerEnd="url(#arrow)" />
      {label && (
        <text
          x={mx}
          y={Math.min(y1, y2) - 10}
          textAnchor="middle"
          className="fill-muted font-mono"
          fontSize={11}
          paintOrder="stroke"
          stroke="rgb(var(--c-bg))"
          strokeWidth={4}
        >
          {label}
        </text>
      )}
    </g>
  );
}

export default function Architecture() {
  return (
    <svg
      viewBox="0 0 950 390"
      className="h-auto w-full"
      role="img"
      aria-label="Architecture: the React UI talks to FastAPI over SSE; FastAPI runs a LangGraph agent that calls Claude and a set of tools guarded by a deterministic policy engine backed by Postgres; Redis holds rate limits, locks and live event pub/sub."
    >
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" className="fill-brand" />
        </marker>
      </defs>
      <Edge from={center("ui", "r")} to={center("api", "l")} label="SSE" />
      <Edge from={center("api", "r")} to={center("agent", "l")} />
      <Edge from={center("agent", "r")} to={center("llm", "l")} label="tool calls" />
      <Edge from={center("agent", "b")} to={center("tools", "t")} />
      <Edge from={center("tools", "r")} to={center("pg", "l")} label="FOR UPDATE" />
      <Edge from={center("api", "r")} to={center("redis", "l")} />
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

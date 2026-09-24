import { ArrowRight, Eye, KeyRound, Scale, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { friendlyError } from "../api";
import { useToast } from "../components/Toaster";
import { Button, Card, Spinner } from "../components/ui";
import { startDemo } from "../lib/demo";
import { useMeta } from "../lib/meta";

const FEATURES = [
  {
    icon: KeyRound,
    title: "Identity from a signed token",
    text: "The agent never trusts who you say you are in chat. Your sandbox customer comes from a JWT.",
  },
  {
    icon: Scale,
    title: "Deterministic policy gate",
    text: "The LLM proposes, code decides. Refunds pass a rules engine and a row lock, so none are approved twice.",
  },
  {
    icon: ShieldAlert,
    title: "Prompt-injection aware",
    text: "Manipulation attempts are flagged, and they can't change the outcome anyway.",
  },
  {
    icon: Eye,
    title: "Every step is visible",
    text: "Tool calls, policy checks and decisions stream live into the reasoning panel and the agent console.",
  },
];

export default function Welcome() {
  const [starting, setStarting] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();
  const { meta } = useMeta();
  const ttl = meta?.demo?.data_ttl_hours ?? 24;

  async function start() {
    setStarting(true);
    try {
      await startDemo();
      navigate("/chat");
    } catch (err) {
      toast(friendlyError(err), "error");
      setStarting(false);
    }
  }

  return (
    <div className="flex h-full overflow-y-auto">
      <div className="relative m-auto flex max-w-5xl flex-col gap-10 px-5 py-12 lg:flex-row lg:items-center">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-10 left-1/2 h-72 w-72 -translate-x-1/2 rounded-full bg-brand/20 blur-3xl"
        />
        <div className="relative flex-1 animate-fade-up">
          <span className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-ok" /> Live demo · no sign-up
          </span>
          <h1 className="mt-5 text-3xl font-bold tracking-tight sm:text-4xl">
            An AI support agent that{" "}
            <span className="bg-gradient-to-r from-indigo-500 to-violet-500 bg-clip-text text-transparent">
              can't be talked into a bad refund.
            </span>
          </h1>
          <p className="mt-4 max-w-xl text-base text-muted">
            You'll get a private sandbox customer with five orders, one for each branch of the refund
            policy. Ask for refunds, try to bend the rules, and watch the agent reason in real time.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Button variant="primary" size="lg" onClick={start} disabled={starting}>
              {starting ? <Spinner /> : null}
              {starting ? "Creating your sandbox…" : "Start the demo"}
              {!starting && <ArrowRight size={16} />}
            </Button>
            <span className="text-xs text-subtle">
              Sandbox data is deleted after {ttl} hours.
            </span>
          </div>
        </div>

        <div className="relative grid flex-1 gap-3 sm:grid-cols-2">
          {FEATURES.map(({ icon: Icon, title, text }, i) => (
            <div key={title} className="animate-fade-up" style={{ animationDelay: `${i * 70}ms` }}>
              <Card className="h-full p-4">
                <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-brand/10 text-brand">
                  <Icon size={18} />
                </div>
                <h2 className="text-sm font-semibold">{title}</h2>
                <p className="mt-1 text-xs leading-relaxed text-muted">{text}</p>
              </Card>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

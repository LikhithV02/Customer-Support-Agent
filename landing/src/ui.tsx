import clsx from "clsx";
import type { ReactNode } from "react";

/** Numbered section header: "01 — SYSTEM DESIGN ———", a big title and a lead. */
export function Section({
  id,
  n,
  eyebrow,
  title,
  lead,
  children,
}: {
  id: string;
  n: string;
  eyebrow: string;
  title: ReactNode;
  lead?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section id={id} className="mx-auto max-w-page scroll-mt-20 px-6 pt-24 sm:pt-32">
      <div className="flex items-center gap-4 font-mono text-xs uppercase tracking-[0.12em] text-muted">
        <span className="text-brand">{n}</span>
        <span>{eyebrow}</span>
        <span aria-hidden className="h-px flex-1 bg-line" />
      </div>
      <h2 className="mt-6 max-w-4xl text-[clamp(2.1rem,4.6vw,3.75rem)] font-semibold leading-[1.02] tracking-[-0.04em]">
        {title}
      </h2>
      {lead && <p className="mt-5 max-w-2xl text-lg text-muted">{lead}</p>}
      <div className="mt-12">{children}</div>
    </section>
  );
}

export function Panel({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={clsx("rounded-2xl border border-line bg-panel", className)}>{children}</div>;
}

export function Figure({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <figure className="m-0 rounded-[18px] border border-line bg-panel p-5 sm:p-6">
      <figcaption className="font-mono text-[11px] uppercase tracking-[0.1em] text-subtle">{caption}</figcaption>
      <div className="mt-4 overflow-x-auto">
        <div className="min-w-[38rem]">{children}</div>
      </div>
    </figure>
  );
}

export function Code({ children }: { children: ReactNode }) {
  return <span className="font-mono text-[0.92em] text-fg">{children}</span>;
}

export function ArrowRight({ size = 16 }: { size?: number }) {
  return (
    <svg aria-hidden width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

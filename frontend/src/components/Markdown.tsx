import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Renders assistant message text as GitHub-flavoured Markdown, styled to match
 * the chat/admin theme. The app has no Tailwind typography plugin, so each
 * element is styled explicitly via the `components` map. Colours inherit from
 * the surrounding bubble (text-fg) unless overridden.
 */
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="space-y-2 break-words leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        // No images either: they'd load third-party URLs from model output.
        disallowedElements={["img"]}
        unwrapDisallowed
        components={{
          p: ({ children }) => <p>{children}</p>,
          strong: ({ children }) => (
            <strong className="font-semibold text-fg">{children}</strong>
          ),
          em: ({ children }) => <em className="italic">{children}</em>,
          ul: ({ children }) => (
            <ul className="list-disc space-y-1 pl-5">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal space-y-1 pl-5">{children}</ol>
          ),
          li: ({ children }) => <li className="pl-1">{children}</li>,
          h1: ({ children }) => (
            <h1 className="mt-3 mb-1 text-base font-semibold text-fg">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="mt-3 mb-1 text-base font-semibold text-fg">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="mt-2 mb-1 text-sm font-semibold text-fg">{children}</h3>
          ),
          // Links render as text: the agent never needs to send one, so a
          // clickable link here could only come from manipulated output. The
          // URL stays visible so nothing is hidden behind link text.
          a: ({ children, href }) => {
            const text = typeof children === "string" ? children : null;
            return (
              <span>
                {children}
                {href && href !== text && (
                  <span className="break-all text-muted"> ({href})</span>
                )}
              </span>
            );
          },
          code: ({ className, children }) => {
            const isBlock = /language-/.test(className ?? "");
            if (isBlock) {
              return (
                <code className="block overflow-x-auto rounded-md bg-surface-2 p-3 font-mono text-xs">
                  {children}
                </code>
              );
            }
            return (
              <code className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[0.85em]">
                {children}
              </code>
            );
          },
          pre: ({ children }) => <pre className="my-2">{children}</pre>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-line pl-3 text-muted">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-3 border-line" />,
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-line px-2 py-1 text-left font-semibold">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-line px-2 py-1">{children}</td>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

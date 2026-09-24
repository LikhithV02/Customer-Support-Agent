import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
      <p className="font-mono text-5xl font-semibold text-brand">404</p>
      <p className="text-sm text-muted">That page doesn't exist.</p>
      <Link to="/" className="text-sm font-medium text-brand hover:underline">
        Back to the demo
      </Link>
    </div>
  );
}

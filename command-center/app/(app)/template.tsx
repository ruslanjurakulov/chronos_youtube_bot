/**
 * A template re-mounts on every navigation (unlike layout), so wrapping the
 * routed page here gives each route a subtle entrance transition. Purely
 * presentational; the `.page-enter` animation is disabled under
 * prefers-reduced-motion (see globals.css).
 */
export default function AppTemplate({ children }: { children: React.ReactNode }) {
  return <div className="page-enter">{children}</div>;
}

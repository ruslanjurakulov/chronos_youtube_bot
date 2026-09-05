/**
 * A template re-mounts on every navigation, which a layout does not. That is
 * what lets a section arrive rather than snap: the same rise-and-settle curve
 * the direction's panel uses, with the page's own sections staggering in after
 * it. prefers-reduced-motion still switches the whole thing off in globals.css.
 */
export default function SectionTemplate({ children }: { children: React.ReactNode }) {
  return <div className="page-rise">{children}</div>;
}

/**
 * A template re-mounts on every navigation, which a layout does not. That is
 * what lets a section arrive rather than snap: the same rise-and-settle curve
 * the direction's panel uses, and the same contained card it is drawn as, so a
 * section opens as a surface on the black ground instead of bleeding into it.
 * prefers-reduced-motion still switches the motion off in globals.css.
 */
export default function SectionTemplate({ children }: { children: React.ReactNode }) {
  return (
    <div className="page-rise">
      <div className="section-card">{children}</div>
    </div>
  );
}

"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";

/**
 * The brand's backdrop: a starfield in real perspective, flying slowly toward
 * the viewer. Each star carries a z, is projected through a focal length, and
 * gains size and brightness as it approaches — so the depth is actual
 * projection rather than three layers pretending. It is Nightshift's own image,
 * drawn in the accent so it belongs to this palette and no other.
 *
 * Opening a section surges the flight forward and eases it back, which is what
 * ties the backdrop to navigation instead of leaving it as wallpaper.
 *
 * It sits at z-index 0 rather than behind everything: a negative z-index would
 * put it under the body's own opaque background, where it draws perfectly and
 * is never seen. The shell above it carries z-10.
 *
 * Deliberately cheap, because it sits under a screen someone reads all day: one
 * 2D canvas, a fixed pool of stars, no allocation per frame, no WebGL. It stops
 * entirely when the tab is hidden, and under prefers-reduced-motion it draws a
 * single still frame and never animates.
 */

const COUNT = 420;
const FOCAL = 420; // perspective strength
const DEPTH = 1400; // how far back stars are seeded
const BASE_SPEED = 0.55;

type Star = { x: number; y: number; z: number; s: number };

export function NightSky() {
  const ref = useRef<HTMLCanvasElement>(null);
  const pathname = usePathname();
  // The loop reads this; navigation never rebuilds the field.
  const surge = useRef(0);

  useEffect(() => {
    surge.current = 1;
  }, [pathname]);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0;
    let h = 0;
    let cx = 0;
    let cy = 0;
    let raf = 0;
    let running = true;
    const stars: Star[] = [];

    const respawn = (st: Star, fresh: boolean) => {
      // Seeded across a wide box so the field still fills the frame at the edges.
      st.x = (Math.random() - 0.5) * w * 2.4;
      st.y = (Math.random() - 0.5) * h * 2.4;
      st.z = fresh ? Math.random() * DEPTH + 1 : DEPTH;
      st.s = 0.5 + Math.random() * 1.3;
    };

    function build() {
      stars.length = 0;
      for (let i = 0; i < COUNT; i++) {
        const st: Star = { x: 0, y: 0, z: 0, s: 1 };
        respawn(st, true);
        stars.push(st);
      }
    }

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas!.clientWidth;
      h = canvas!.clientHeight;
      cx = w / 2;
      cy = h / 2;
      canvas!.width = Math.floor(w * dpr);
      canvas!.height = Math.floor(h * dpr);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      build();
    }

    function draw() {
      ctx!.clearRect(0, 0, w, h);

      const speed = BASE_SPEED * (1 + surge.current * 9);
      for (const st of stars) {
        if (!reduced) {
          st.z -= speed;
          if (st.z < 1) respawn(st, false);
        }
        const k = FOCAL / st.z;
        const px = cx + st.x * k;
        const py = cy + st.y * k;
        if (px < -20 || px > w + 20 || py < -20 || py > h + 20) continue;

        // Nearer is bigger and brighter — the whole cue that this has depth.
        // A real floor on brightness: a far star must still be a star, not a
        // pixel at 6% that no screen shows. Near ones then pull clearly ahead.
        const near = 1 - st.z / DEPTH;
        const r = Math.max(0.65, st.s * k * 1.7);
        ctx!.globalAlpha = Math.min(0.9, 0.2 + near * 0.7);
        ctx!.fillStyle = "#a1d0fc";
        ctx!.beginPath();
        ctx!.arc(px, py, Math.min(r, 2.6), 0, Math.PI * 2);
        ctx!.fill();
      }
      ctx!.globalAlpha = 1;

      if (surge.current > 0) surge.current = Math.max(0, surge.current - 0.014);
    }

    function frame() {
      if (!running) return;
      draw();
      raf = requestAnimationFrame(frame);
    }

    function onVisibility() {
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(raf);
      } else if (!reduced) {
        running = true;
        raf = requestAnimationFrame(frame);
      }
    }

    resize();
    if (reduced) {
      draw();
    } else {
      raf = requestAnimationFrame(frame);
    }
    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      running = false;
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return (
    <canvas
      ref={ref}
      aria-hidden
      className="pointer-events-none fixed inset-0 z-0 h-full w-full"
    />
  );
}

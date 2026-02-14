"use client";

import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Sparkles } from "lucide-react";

import { useEffect, useRef, useState } from "react";

import { useGSAP } from "@gsap/react";

// Register ScrollTrigger plugin
if (typeof window !== "undefined") {
  gsap.registerPlugin(ScrollTrigger);
}

export default function ComplexityToClarity() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isDesktop, setIsDesktop] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(min-width: 768px)");
    const update = () => setIsDesktop(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  useGSAP(
    () => {
      if (!isDesktop) return;
      const scramble = containerRef.current?.querySelector(".scramble-text");
      const clear = containerRef.current?.querySelector(".clear-text");
      const beams = containerRef.current?.querySelectorAll(".beam") || [];

      if (!scramble || !clear) return;

      // Set initial states
      gsap.set(clear, { opacity: 0, scale: 0.95 });
      gsap.set(".clarity-badge", { y: 20, opacity: 0 });
      gsap.set(beams, { opacity: 0, scaleY: 0.5 });

      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: containerRef.current,
          start: "center center",
          // Reduced scroll duration for tighter experience
          end: "+=150%",
          pin: true,
          scrub: 2,
        },
      });

      // Extended hold period - content stays visible and centered longer
      // Start transition at 50% of scroll (more time to read the first state)
      tl.to(
        scramble,
        {
          opacity: 0,
          filter: "blur(12px)",
          scale: 0.9,
          duration: 1.2,
        },
        0.5,
      )
        .to(
          clear,
          {
            opacity: 1,
            filter: "blur(0px)",
            scale: 1,
            duration: 1.2,
          },
          0.9,
        )
        .to(
          ".clarity-badge",
          {
            y: 0,
            opacity: 1,
            duration: 0.6,
          },
          1.3,
        );

      // Animate beams - start with the transition
      tl.to(
        beams,
        {
          opacity: 0.08,
          scaleY: 1.5,
          stagger: 0.15,
          duration: 1.2,
        },
        0.5,
      );

      // useGSAP handles cleanup automatically via revert()
    },
    { scope: containerRef, dependencies: [isDesktop] },
  );

  return (
    <section
      ref={containerRef}
      className="relative bg-background text-foreground flex flex-col items-center justify-center overflow-hidden py-16 md:py-0 min-h-[120vh] md:min-h-0 md:h-[200vh]"
    >
      {/* Ambient glow - warm tones */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-primary/5 rounded-full blur-[180px] pointer-events-none" />

      {/* Background "Complexity" - Dense Jargon Pattern */}
      <div className="absolute inset-0 opacity-[0.03] select-none pointer-events-none font-mono text-[10px] leading-none whitespace-pre overflow-hidden text-foreground/40 dark:text-foreground/20">
        {Array.from({ length: 80 }).map((_, i) => (
          <div key={i}>
            {"PURSUANT TO SUBSECTION 4(A)(II) THE LICENSOR HEREBY DISCLAIMS ALL WARRANTIES EXPRESS OR IMPLIED INCLUDING BUT NOT LIMITED TO MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE NOTWITHSTANDING ANY CONSEQUENTIAL DAMAGES ".repeat(
              5,
            )}
          </div>
        ))}
      </div>

      {/* Content Container */}
      <div className="relative z-10 max-w-5xl text-center px-4">
        {/* Scrambled/Complex State */}
        <div className="scramble-text hidden md:block">
          <h2 className="text-4xl md:text-6xl lg:text-7xl font-display font-bold mb-8 leading-[1.1] tracking-tight">
            <span className="text-foreground">Dense. Overwhelming.</span> <br />
            <span className="text-muted-foreground/60 font-serif italic font-normal tracking-normal">
              Designed to obscure.
            </span>
          </h2>
          <p className="text-muted-foreground text-lg md:text-2xl font-medium tracking-tight max-w-3xl mx-auto">
            The average legal policy takes{" "}
            <span className="text-primary font-semibold">45 minutes</span> to
            parse. <br />
            Most sign without ever reading the terms.
          </p>
        </div>

        {/* Clear/Illuminated State */}
        <div className="clear-text hidden md:flex absolute inset-0 flex-col items-center justify-center opacity-0 pointer-events-none">
          <div className="clarity-badge mb-10 flex items-center gap-3 bg-primary/10 border border-primary/20 px-6 py-2.5 rounded-full backdrop-blur-xl">
            <Sparkles className="w-5 h-5 text-primary" />
            <span className="text-xs font-medium tracking-wider uppercase text-primary">
              Crystal Clear
            </span>
          </div>

          <h2 className="text-5xl md:text-7xl lg:text-8xl font-display font-bold mb-10 leading-[0.9] tracking-tight">
            <span className="text-foreground">Clarity</span>{" "}
            <span className="text-gradient-warm font-serif italic font-normal tracking-normal">
              surfaces.
            </span>
          </h2>

          <p className="text-muted-foreground text-xl md:text-2xl max-w-3xl leading-relaxed">
            Clausea dives deep, extracting the essential risks. <br />
            <span className="text-foreground/90 font-medium">
              No jargon. No hidden clauses.
            </span>{" "}
            Just the clear facts you need.
          </p>

          {/* Social Proof */}
          <div className="mt-16 flex items-center gap-6">
            <div className="flex -space-x-3">
              {[1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  className="w-11 h-11 rounded-full border-2 border-background bg-linear-to-br from-primary/20 to-secondary/20 flex items-center justify-center text-xs font-bold text-primary"
                >
                  {["JD", "AS", "MK", "LP"][i - 1]}
                </div>
              ))}
            </div>
            <p className="text-sm font-medium text-muted-foreground">
              Trusted by{" "}
              <span className="text-primary font-semibold">5,000+</span> Legal
              Teams
            </p>
          </div>
        </div>

        {/* Mobile Static State */}
        <div className="md:hidden space-y-6 text-center mt-10">
          <div className="inline-flex items-center gap-3 bg-primary/10 border border-primary/20 px-5 py-2 rounded-full text-primary text-xs font-semibold tracking-widest uppercase">
            <Sparkles className="h-4 w-4" /> Clarity Mode
          </div>
          <h2 className="text-3xl font-display font-bold leading-tight">
            Legal speak, translated into{" "}
            <span className="text-gradient-warm font-serif italic">
              real words
            </span>
            .
          </h2>
          <p className="text-muted-foreground text-base leading-relaxed">
            Clausea highlights the risks, commitments, and rights so you can
            make confident decisions without reading a 40-page PDF on your
            phone.
          </p>
          <div className="flex flex-col items-center gap-3">
            <div className="flex -space-x-3">
              {["JD", "AS", "MK", "LP"].map((initials) => (
                <div
                  key={initials}
                  className="w-10 h-10 rounded-full border-2 border-background bg-linear-to-br from-primary/30 to-secondary/20 flex items-center justify-center text-xs font-bold text-primary"
                >
                  {initials}
                </div>
              ))}
            </div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Trusted by 5,000+ legal teams
            </p>
          </div>
        </div>
      </div>

      {/* Decorative Light Beams - Warm-themed */}
      <div className="absolute inset-0 pointer-events-none -z-10 overflow-hidden">
        {[...Array(6)].map((_, i) => (
          <div
            key={i}
            className="beam absolute top-[-50%] w-px h-[200%] origin-top opacity-0"
            style={{
              left: `${15 + i * 14}%`,
              background: `linear-gradient(180deg, transparent 0%, hsla(18, 55%, 54%, 0.15) 50%, transparent 100%)`,
              transform: `rotate(${-5 + i * 2}deg)`,
            }}
          />
        ))}
      </div>

      {/* Bottom gradient */}
      <div className="absolute bottom-0 left-0 right-0 h-40 bg-linear-to-t from-background to-transparent pointer-events-none" />
    </section>
  );
}

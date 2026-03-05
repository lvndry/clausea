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
          start: "top top",
          end: "+=140%",
          scrub: 1.5,
          pin: true,
          pinSpacing: true,
          anticipatePin: 1,
          invalidateOnRefresh: true,
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

      ScrollTrigger.refresh();

      // useGSAP handles cleanup automatically via revert()
    },
    { scope: containerRef, dependencies: [isDesktop] },
  );

  return (
    <section
      ref={containerRef}
      className="col-span-12 relative bg-background border-b border-border text-foreground flex flex-col items-center justify-center overflow-hidden py-16 md:py-0 min-h-[80vh] md:min-h-screen"
    >
      {/* Background "Complexity" - Dense Jargon Pattern */}
      <div className="absolute inset-0 opacity-[0.05] select-none pointer-events-none font-mono text-[10px] leading-tight whitespace-pre overflow-hidden text-foreground">
        {Array.from({ length: 80 }).map((_, i) => (
          <div key={i}>
            {"PURSUANT TO SUBSECTION 4(A)(II) THE LICENSOR HEREBY DISCLAIMS ALL WARRANTIES EXPRESS OR IMPLIED INCLUDING BUT NOT LIMITED TO MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE NOTWITHSTANDING ANY CONSEQUENTIAL DAMAGES ".repeat(
              5,
            )}
          </div>
        ))}
      </div>

      {/* Content Container */}
      <div className="relative z-10 max-w-5xl text-center px-6 md:px-10 w-full">
        {/* Scrambled/Complex State */}
        <div className="scramble-text hidden md:block">
          <h2 className="text-4xl md:text-[110px] font-display font-medium mb-12 leading-[0.9] tracking-tight text-foreground">
            Dense. Overwhelming. <br />
            <span className="text-muted-foreground font-serif italic font-normal tracking-normal">
              Designed to obscure.
            </span>
          </h2>
          <p className="text-muted-foreground text-lg md:text-xl max-w-2xl mx-auto leading-relaxed">
            The average legal policy takes{" "}
            <span className="text-foreground font-medium">45 minutes</span> to
            parse. <br />
            Most sign without ever reading the terms.
          </p>
        </div>

        {/* Clear/Illuminated State */}
        <div className="clear-text hidden md:flex absolute inset-0 flex-col items-center justify-center opacity-0 pointer-events-none px-6 w-full">
          <div className="clarity-badge mb-12 flex items-center gap-3 border border-foreground bg-background px-6 py-2.5">
            <Sparkles className="w-5 h-5 text-foreground" />
            <span className="text-[10px] md:text-xs font-medium tracking-widest uppercase text-foreground">
              Crystal Clear
            </span>
          </div>

          <h2 className="text-5xl md:text-[140px] font-display font-medium mb-12 leading-[0.85] tracking-tight text-foreground -ml-2">
            Clarity
            <br />
            <span className="text-muted-foreground font-serif italic font-normal tracking-normal">
              surfaces.
            </span>
          </h2>

          <p className="text-muted-foreground text-lg md:text-xl max-w-2xl leading-relaxed">
            Clausea dives deep, extracting the essential risks. <br />
            <span className="text-foreground font-medium">
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
                  className="w-11 h-11 rounded-full border border-background bg-foreground flex items-center justify-center text-[10px] font-medium text-background"
                >
                  {["JD", "AS", "MK", "LP"][i - 1]}
                </div>
              ))}
            </div>
            <p className="text-[10px] uppercase tracking-widest font-medium text-muted-foreground">
              Trusted by <span className="text-foreground">5,000+</span> Legal
              Teams
            </p>
          </div>
        </div>

        {/* Mobile Static State */}
        <div className="md:hidden space-y-6 text-center mt-10">
          <div className="inline-flex items-center gap-3 border border-foreground bg-background px-5 py-2 text-foreground text-[10px] font-medium tracking-widest uppercase">
            <Sparkles className="h-4 w-4" /> Clarity Mode
          </div>
          <h2 className="text-5xl font-display font-medium leading-[0.9] text-foreground">
            Legal speak, translated into{" "}
            <span className="text-muted-foreground font-serif italic">
              real words
            </span>
            .
          </h2>
          <p className="text-muted-foreground text-sm leading-relaxed max-w-[280px] mx-auto">
            Clausea highlights the risks, commitments, and rights so you can
            make confident decisions without reading a 40-page PDF on your
            phone.
          </p>
          <div className="flex flex-col items-center gap-4 pt-4">
            <div className="flex -space-x-3">
              {["JD", "AS", "MK", "LP"].map((initials) => (
                <div
                  key={initials}
                  className="w-10 h-10 rounded-full border border-background bg-foreground flex items-center justify-center text-[10px] font-medium text-background"
                >
                  {initials}
                </div>
              ))}
            </div>
            <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest">
              Trusted by 5,000+ legal teams
            </p>
          </div>
        </div>
      </div>

      {/* Decorative vertical lines */}
      <div className="absolute inset-0 pointer-events-none -z-10 flex justify-between px-6 md:px-10 opacity-10">
        <div className="w-px h-full bg-foreground" />
        <div className="hidden md:block w-px h-full bg-foreground" />
        <div className="w-px h-full bg-foreground" />
      </div>
    </section>
  );
}

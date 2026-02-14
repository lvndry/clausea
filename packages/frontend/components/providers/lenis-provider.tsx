"use client";

import gsap from "gsap";
import { ScrollTrigger } from "gsap/dist/ScrollTrigger";
import Lenis from "lenis";
import "lenis/dist/lenis.css";

import { useEffect } from "react";

if (typeof window !== "undefined") {
  gsap.registerPlugin(ScrollTrigger);
}

export function LenisProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    // Initialize a new Lenis instance for smooth scrolling
    const lenis = new Lenis({
      lerp: 0.1,
      duration: 1.2,
      smoothWheel: true,
      // Prevent Lenis from intercepting scroll events on nested scrollable containers
      prevent: (node) => {
        // Check if the node or any parent has overflow-y-auto
        let element = node as HTMLElement;
        while (element && element !== document.body) {
          const style = window.getComputedStyle(element);
          if (
            style.overflowY === "auto" ||
            style.overflowY === "scroll" ||
            element.hasAttribute("data-lenis-prevent")
          ) {
            return true;
          }
          element = element.parentElement as HTMLElement;
        }
        return false;
      },
    });

    // Synchronize Lenis scrolling with GSAP's ScrollTrigger plugin
    lenis.on("scroll", ScrollTrigger.update);

    // Add Lenis's requestAnimationFrame (raf) method to GSAP's ticker
    // This ensures Lenis's smooth scroll animation updates on each GSAP tick
    // Store the callback so we can properly remove it on cleanup
    function rafCallback(time: number) {
      lenis.raf(time * 1000); // Convert time from seconds to milliseconds
    }
    gsap.ticker.add(rafCallback);

    // Disable lag smoothing in GSAP to prevent any delay in scroll animations
    gsap.ticker.lagSmoothing(0);

    // Refresh ScrollTrigger after layout settles
    const refreshTimeout = setTimeout(() => {
      ScrollTrigger.refresh();
    }, 100);

    return () => {
      clearTimeout(refreshTimeout);
      // Remove the same callback reference that was added
      gsap.ticker.remove(rafCallback);
      lenis.destroy();
    };
  }, []);

  return <>{children}</>;
}

"use client";

import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

import { useLayoutEffect, useRef } from "react";

/**
 * GSAP Plugin Registration Component
 *
 * This component ensures GSAP plugins are properly registered before any
 * animations run. Must be placed at the root of the app layout.
 */
export function GSAPInit() {
  const isRegistered = useRef(false);

  useLayoutEffect(() => {
    // Only register once (handles React Strict Mode double-mount)
    if (!isRegistered.current) {
      gsap.registerPlugin(ScrollTrigger);

      // Configure ScrollTrigger defaults for consistency
      ScrollTrigger.defaults({
        toggleActions: "play none none reverse",
        markers: false,
      });

      isRegistered.current = true;
    }

    // Refresh ScrollTrigger on window resize
    function handleResize() {
      ScrollTrigger.refresh();
    }

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      // Don't kill all ScrollTriggers here - let individual components
      // handle their own cleanup to avoid issues with Strict Mode
    };
  }, []);

  return null;
}

export default GSAPInit;

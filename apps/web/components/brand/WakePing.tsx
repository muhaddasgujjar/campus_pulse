"use client";

import { useEffect } from "react";

import { wakeApi } from "@/lib/wake";

/** Renders nothing. Pings the API once on page load so a sleeping Render service starts. */
export function WakePing() {
  useEffect(() => {
    wakeApi();
  }, []);
  return null;
}

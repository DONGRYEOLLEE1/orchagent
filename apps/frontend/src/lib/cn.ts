// Phase 3.7 — single source of truth for the cn(...) class-name helper.
// Combines clsx + tailwind-merge so duplicate Tailwind utility classes are
// collapsed (e.g. `cn("p-2", "p-4")` → `"p-4"`).

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

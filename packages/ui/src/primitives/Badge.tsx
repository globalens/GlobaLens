import type { ReactNode } from "react";

import styles from "./badge.module.css";

export interface BadgeProps {
  tone?: "neutral" | "warning" | undefined;
  /** "inline": one line of mono caps. "block": a sentence that wraps. */
  size?: "inline" | "block" | undefined;
  children: ReactNode;
}

/** Status in words with an icon beside them: never colour alone (plan §4). */
export function Badge({ tone = "neutral", size = "inline", children }: BadgeProps) {
  return (
    <span className={styles.badge} data-tone={tone} data-size={size}>
      <span className={styles.icon} aria-hidden="true" />
      <span>{children}</span>
    </span>
  );
}

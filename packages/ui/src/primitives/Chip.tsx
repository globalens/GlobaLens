import type { ReactNode } from "react";

import styles from "./chip.module.css";

export interface ChipProps {
  pressed: boolean;
  onPress: () => void;
  /** The key that toggles it, shown before the label (1 EN, 2 AR, ...). */
  keyHint?: string | undefined;
  children: ReactNode;
}

/** A toggle button, used for the language chips (task 15). */
export function Chip({ pressed, onPress, keyHint, children }: ChipProps) {
  return (
    <button type="button" className={styles.chip} aria-pressed={pressed} onClick={onPress}>
      {keyHint !== undefined && <kbd>{keyHint}</kbd>}
      {children}
    </button>
  );
}

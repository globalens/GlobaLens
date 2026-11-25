import type { ReactNode } from "react";

import styles from "./panel.module.css";

export interface PanelProps {
  /** The region's accessible name. */
  label: string;
  header?: ReactNode;
  footer?: ReactNode;
  children?: ReactNode;
  className?: string | undefined;
}

/** A labelled surface with an optional header and footer (frame 1, the 360 px panel). */
export function Panel({ label, header, footer, children, className }: PanelProps) {
  return (
    <aside aria-label={label} className={className ? `${styles.panel} ${className}` : styles.panel}>
      {header !== undefined && <header className={styles.header}>{header}</header>}
      <div className={styles.body}>{children}</div>
      {footer !== undefined && <footer className={styles.footer}>{footer}</footer>}
    </aside>
  );
}

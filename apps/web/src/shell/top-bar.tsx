// The 44 px top bar (frame 1; 48 px on a phone, frame 3). In P1 it holds the brand only: the
// language chips and the two-clock badge arrive with task 15, and later controls are not shown
// disabled (Q5).
import { strings } from "@globalens/ui";
import Link from "next/link";

import styles from "./shell.module.css";

export function TopBar() {
  return (
    <header className={styles.topBar}>
      <Link href="/" className={styles.brand} aria-label={strings.brand.home}>
        <span className={styles.brandMark} aria-hidden="true" />
        {strings.brand.name}
      </Link>
    </header>
  );
}

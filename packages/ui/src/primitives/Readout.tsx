import styles from "./readout.module.css";

export interface ReadoutProps {
  value: string;
  label: string;
}

/** A figure with its unit, read as one phrase ("214 articles"). */
export function Readout({ value, label }: ReadoutProps) {
  return (
    <div className={styles.readout}>
      <span className={styles.value}>{value}</span> <span className={styles.label}>{label}</span>
    </div>
  );
}

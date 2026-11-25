import { directionOf } from "../lang";
import { copiesLabel } from "../strings";
import { Time } from "./Time";
import styles from "./list-row.module.css";

export interface ListRowProps {
  /** The original title. Untrusted text: React renders it as a text node, never as markup. */
  title: string;
  /** BCP 47; the title's `dir` follows from it, `auto` only when it is unknown (Q6). */
  lang: string;
  href: string;
  outlet: string;
  at: number;
  now: number;
  timeZone?: string | undefined;
  copies?: { copies: number; outlets: number } | undefined;
}

function httpUrl(href: string): string | null {
  try {
    const url = new URL(href);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

/** One headline: the whole title is the link out; outlet and time sit in <bdi>. */
export function ListRow({ title, lang, href, outlet, at, now, timeZone, copies }: ListRowProps) {
  const dir = directionOf(lang);
  const link = httpUrl(href);
  return (
    <li className={styles.row}>
      {link ? (
        <a className={styles.title} lang={lang} dir={dir} href={link} target="_blank" rel="noopener noreferrer">
          {title}
        </a>
      ) : (
        <span className={styles.title} lang={lang} dir={dir}>
          {title}
        </span>
      )}
      <div className={styles.meta}>
        <span className={styles.lang}>{lang}</span>
        <bdi>{outlet}</bdi>
        <bdi>
          <Time at={at} now={now} timeZone={timeZone} />
        </bdi>
        {link && (
          <span className={styles.out} aria-hidden="true">
            ↗
          </span>
        )}
      </div>
      {copies && <span className={styles.copies}>{copiesLabel(copies.copies, copies.outlets)}</span>}
    </li>
  );
}

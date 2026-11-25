// The not-found page (404.html in the export). It also carries the story link rule: an unknown
// /story/<id> lands on the globe with ?story=<id> (master plan §4; design note §9 task 12).
import { strings } from "@globalens/ui";
import Link from "next/link";

import { storyLinkScript } from "../story/link";
import styles from "./not-found.module.css";

export default function NotFound() {
  return (
    <main className={styles.page}>
      <script dangerouslySetInnerHTML={{ __html: storyLinkScript() }} />
      <h1 className={styles.title}>{strings.notFound.title}</h1>
      <p className={styles.body}>{strings.notFound.body}</p>
      <p className={styles.body}>
        <Link href="/" className={styles.link}>
          {strings.notFound.back}
        </Link>
      </p>
    </main>
  );
}

// The plain P1 states (design note Q7; frame 2, column C), with the plan's own copy.
import { Badge, formatUtcClock, interpolate, staleCopy, strings, Time } from "@globalens/ui";

import type { PanelBlock } from "./state";
import styles from "./shell.module.css";

export function StateBlocks({ blocks, onRetry }: { blocks: PanelBlock[]; onRetry: () => void }) {
  return (
    <div className={styles.states} role="status">
      {blocks.map((block) => (
        <div key={block.kind} className={styles.state} data-state={block.kind}>
          <Block block={block} onRetry={onRetry} />
        </div>
      ))}
    </div>
  );
}

function Block({ block, onRetry }: { block: PanelBlock; onRetry: () => void }) {
  switch (block.kind) {
    case "loading":
      return (
        <div aria-busy="true">
          <span className="visually-hidden">{strings.states.loading}</span>
          <div className={`${styles.skeleton} ${styles.skeletonLong}`} />
          <div className={`${styles.skeleton} ${styles.skeletonMid}`} />
          <div className={`${styles.skeleton} ${styles.skeletonShort}`} />
        </div>
      );
    case "failed":
      return (
        <>
          <p className={styles.copy}>
            <b>{strings.states.failed}</b>
            {block.lastDataAt !== null && (
              <>
                {" "}
                {interpolate(strings.states.failedShowing, { time: <Time key="time" at={block.lastDataAt} /> })}
              </>
            )}
          </p>
          <button type="button" className={styles.button} onClick={onRetry}>
            {strings.states.retry}
          </button>
        </>
      );
    case "stale":
      return (
        <Badge tone="warning" size="block">
          {staleCopy({ streams: block.streams, sinceUtc: formatUtcClock(block.since) })}
        </Badge>
      );
    case "paused":
      return (
        <Badge tone="warning" size="block">
          {strings.states.paused}
        </Badge>
      );
    case "empty":
      return (
        <p className={styles.copy}>
          <b>{strings.states.empty}</b>
        </p>
      );
    case "no-webgl":
      return <p className={styles.copy}>{strings.states.noWebgl}</p>;
  }
}

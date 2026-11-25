// The persistent globe (master plan §6, "App framework"; design note §4): mounted once for every
// page in this group, so moving between them never reloads it.
import { strings } from "@globalens/ui";
import type { ReactNode } from "react";

import { firstPaintScript } from "../../globe/first-paint";
import { GlobeProvider } from "../../globe/provider";
import { GlobeStage } from "../../globe/stage";
import { Shell } from "../../shell/shell";

export default function GlobeLayout({ children }: { children: ReactNode }) {
  return (
    <GlobeProvider>
      <main aria-label={strings.globe.region}>
        <h1 className="visually-hidden">{strings.meta.title}</h1>
        <GlobeStage />
        {/* Runs as the parser reaches it, before React loads: picks the globe for this time zone. */}
        <script dangerouslySetInnerHTML={{ __html: firstPaintScript() }} />
      </main>
      <Shell>{children}</Shell>
    </GlobeProvider>
  );
}

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";

import { Badge, Chip, ListRow, Panel, Readout, Time } from "./index";

const html = (node: React.ReactElement) => renderToStaticMarkup(node);
const t = Date.parse("2026-11-25T14:02:09Z");

describe("Panel", () => {
  test("is a labelled region", () => {
    const out = html(<Panel label="In the Lens">body</Panel>);
    expect(out).toMatch(/^<aside[^>]* aria-label="In the Lens"/);
    expect(out).toContain("body");
  });
});

describe("Chip", () => {
  test("is a toggle button with its key shown and its state exposed", () => {
    const out = html(<Chip pressed keyHint="2" onPress={() => {}}>AR</Chip>);
    expect(out).toMatch(/^<button[^>]* type="button"/);
    expect(out).toContain('aria-pressed="true"');
    expect(out).toMatch(/<kbd[^>]*>2<\/kbd>/);
    expect(out).toContain("AR");
  });
});

describe("Badge", () => {
  test("a warning always carries an icon and words, never colour alone", () => {
    const out = html(<Badge tone="warning">GDELT hasn’t published</Badge>);
    expect(out).toContain('data-tone="warning"');
    expect(out).toMatch(/<span[^>]* aria-hidden="true"[^>]*>/);
    expect(out).toContain("GDELT hasn’t published");
  });
});

describe("Readout", () => {
  test("a number with its unit label", () => {
    const out = html(<Readout value="214" label="articles" />);
    expect(out).toContain("214");
    expect(out).toContain("articles");
  });
});

describe("Time: the viewer's zone, UTC on hover", () => {
  test("a <time> with a machine-readable datetime and the UTC time as its title", () => {
    const out = html(<Time at={t} now={t} timeZone="Europe/Kyiv" />);
    expect(out).toBe('<time dateTime="2026-11-25T14:02:09.000Z" title="2026-11-25 14:02 UTC">16:02</time>');
  });
});

describe("ListRow: a headline in its own script and direction", () => {
  const row = (lang: string) =>
    html(
      <ListRow
        title="مجلس المدينة يقر خطة جديدة لإمدادات المياه"
        lang={lang}
        href="https://akhbar-alnil.example/a/1"
        outlet="akhbar-alnil.example"
        at={t}
        now={t}
        timeZone="UTC"
        copies={{ copies: 11, outlets: 4 }}
      />,
    );

  test("the title is the link out, with lang and dir from the language", () => {
    const out = row("ar");
    expect(out).toMatch(/<a[^>]* lang="ar"[^>]* dir="rtl"[^>]* href="https:\/\/akhbar-alnil\.example\/a\/1"/);
    expect(out).toContain("rel=\"noopener noreferrer\"");
  });

  test("outlet and time sit in <bdi> so they never reorder", () => {
    const out = row("ar");
    expect(out).toContain("<bdi>akhbar-alnil.example</bdi>");
    expect(out).toMatch(/<bdi><time [^>]*>14:02<\/time><\/bdi>/);
  });

  test("the copies chip counts copies and outlets", () => {
    expect(row("ar")).toContain("+11 copies · 4 outlets");
  });

  test("an unknown language falls back to dir=auto", () => {
    expect(row("und")).toMatch(/<a[^>]* lang="und"[^>]* dir="auto"/);
  });

  test("a title with markup in it renders as text", () => {
    const out = html(
      <ListRow title={'<img src=x onerror="alert(1)">'} lang="en" href="https://x.example/" outlet="x.example" at={t} now={t} />,
    );
    expect(out).not.toContain("<img");
    expect(out).toContain("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;");
  });

  test("a link that is not http(s) is not rendered as a link", () => {
    const out = html(
      <ListRow title="x" lang="en" href={"javascript:alert(1)"} outlet="x.example" at={t} now={t} />,
    );
    expect(out).not.toContain("javascript:");
    expect(out).not.toMatch(/<a /);
  });
});

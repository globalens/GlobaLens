// The story link rule (plan §4 Layout and §6; design note §9 task 12): every story's own link is
// the globe with ?story=<id>. A /story/<id>/ page exists only for a pre-rendered top story (P4);
// the not-found page turns any other /story/<id> into the ?story= link.

/**
 * The globe link for a /story/<id> path, or null. The id is one path segment, at most 200
 * characters once decoded, and is encoded again so it can only ever be the story parameter.
 *
 * Self-contained, because the not-found page's inline script carries its source.
 */
export function storyLinkTarget(pathname: string): string | null {
  const match = /^\/story\/([^/]+)\/?$/.exec(pathname);
  if (!match || !match[1]) return null;
  let id: string;
  try {
    id = decodeURIComponent(match[1]);
  } catch {
    return null;
  }
  if (id.length === 0 || id.length > 200) return null;
  return "/?story=" + encodeURIComponent(id);
}

interface StoryLocation {
  pathname: string;
  replace(url: string): void;
}

/** What the not-found page's inline script does. Self-contained, like storyLinkTarget. */
export function redirectStoryLink(location: StoryLocation, target?: (pathname: string) => string | null): void {
  const to = (target || storyLinkTarget)(location.pathname);
  if (to) location.replace(to);
}

/** The inline script's source: both functions above, run on the real location. */
export function storyLinkScript(): string {
  return `(${redirectStoryLink.toString()})(location,${storyLinkTarget.toString()})`;
}

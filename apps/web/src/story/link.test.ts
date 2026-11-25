import { describe, expect, test } from "vitest";

import { redirectStoryLink, storyLinkScript, storyLinkTarget } from "./link";

describe("storyLinkTarget: an unknown /story/<id> lands on the globe with ?story=<id>", () => {
  test.each([
    ["/story/abc123", "/?story=abc123"],
    ["/story/abc123/", "/?story=abc123"],
    ["/story/2027-02-24-flood_a", "/?story=2027-02-24-flood_a"],
    ["/story/a%20b", "/?story=a%20b"], // decoded, then encoded again
    ["/story/%D8%B3%D9%88%D8%AF%D8%A7%D9%86", "/?story=%D8%B3%D9%88%D8%AF%D8%A7%D9%86"],
    ["/story/a&b=c", "/?story=a%26b%3Dc"], // cannot add a parameter of its own
  ])("%s -> %s", (path, target) => {
    expect(storyLinkTarget(path)).toBe(target);
  });

  test.each([
    ["/"],
    ["/story"],
    ["/story/"],
    ["/story//"],
    ["/story/a/b"],
    ["/stories/abc"],
    ["/STORY/abc"],
    ["/x/story/abc"],
    ["/story/%E0%A4%A"], // broken percent-encoding
    ["/story/" + "x".repeat(201)],
  ])("%s is not a story link", (path) => {
    expect(storyLinkTarget(path)).toBeNull();
  });

  test("200 characters is the longest id", () => {
    expect(storyLinkTarget("/story/" + "x".repeat(200))).toBe("/?story=" + "x".repeat(200));
  });
});

describe("the not-found page's inline script", () => {
  function fakeLocation(pathname: string) {
    const replaced: string[] = [];
    return { location: { pathname, replace: (url: string) => replaced.push(url) }, replaced };
  }

  test("replaces the location for a story link, and only then", () => {
    const story = fakeLocation("/story/abc");
    redirectStoryLink(story.location);
    expect(story.replaced).toEqual(["/?story=abc"]);

    const other = fakeLocation("/missing");
    redirectStoryLink(other.location);
    expect(other.replaced).toEqual([]);
  });

  test("is self-contained: it runs on its own and does the same", () => {
    const { location, replaced } = fakeLocation("/story/xyz/");
    new Function("location", storyLinkScript())(location);
    expect(replaced).toEqual(["/?story=xyz"]);
  });
});

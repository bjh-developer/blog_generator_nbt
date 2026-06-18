import fs from "node:fs";
import path from "node:path";
import type { StoryBrief } from "./types";

const DIR = path.join(process.cwd(), "content", "breakdowns");

export function allSlugs(): string[] {
  if (!fs.existsSync(DIR)) return [];
  return fs.readdirSync(DIR)
    .filter((f) => f.endsWith(".json"))
    .map((f) => f.replace(/\.json$/, ""));
}

export function getStory(slug: string): StoryBrief {
  return JSON.parse(fs.readFileSync(path.join(DIR, `${slug}.json`), "utf-8"));
}

export function allStories(): StoryBrief[] {
  return allSlugs().map(getStory);
}

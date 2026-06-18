import type { TimelineKind } from "./types";

export const palette = {
  cream: "#fff4de", ink: "#352757", purple: "#784eb5", lilac: "#cdc5fc",
  orchid: "#e2a9f1", pink: "#faaef1", blue: "#5675f0", navy: "#0c3571",
  cyan: "#88e5f6", orange: "#ff914d", peach: "#ffb169",
} as const;

export const chartColors = [palette.blue, palette.orange, palette.cyan, palette.peach, palette.navy];

// per-section accent rotation so adjacent sections differ (not all purple)
export const sectionAccents = [
  palette.orange, palette.purple, palette.blue, palette.pink, palette.cyan, palette.peach,
];
export const accentFor = (i: number) => sectionAccents[i % sectionAccents.length];

export const kindColor: Record<TimelineKind, string> = {
  founder_story: palette.orange,
  product: palette.purple,
  funding: palette.blue,
  inflection: palette.cyan,
  user_delight: palette.pink,
};

export const kindLabel: Record<TimelineKind, string> = {
  founder_story: "Founder Story",
  product: "Product",
  funding: "Funding",
  inflection: "Inflection",
  user_delight: "User Delight",
};

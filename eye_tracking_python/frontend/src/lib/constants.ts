import type { TaskType } from "@/lib/types";

// The exact, approved disclaimer. Used verbatim across the site.
export const DISCLAIMER =
  "This software is a research prototype for eye-tracking data collection. " +
  "It does not diagnose, treat, predict, or screen for Parkinson's disease " +
  "or any other medical condition. Clinical use would require validation, " +
  "regulatory review, and healthcare professional oversight.";

export const SHORT_DISCLAIMER =
  "Ocula is not a diagnostic tool. It does not diagnose, treat, predict, or " +
  "screen for Parkinson's disease or any other condition.";

// Founder details (used on the About page). Sourced from the resume — no
// invented credentials.
export const FOUNDER = {
  name: "Abhinav Kakkera",
  role: "Student researcher · Founder of Ocula",
  school: "Thomas Jefferson High School for Science and Technology (TJHSST)",
  initials: "AK",
  photo: "/founder.jpg",
};

export interface ActivityDef {
  slug: TaskType;
  name: string;          // friendly name
  technical: string;     // technical name
  short: string;         // one-line description
  duration: string;      // estimated duration
  icon: string;          // emoji glyph
  measures: string;      // what it observes (research-only language)
}

export const ACTIVITIES: ActivityDef[] = [
  {
    slug: "prosaccade",
    name: "Look Toward the Dot",
    technical: "Pro-saccade",
    short: "Look at the center dot. When another dot appears, look toward it.",
    duration: "~1–2 min",
    icon: "→",
    measures: "How quickly and accurately the eyes move toward a new target.",
  },
  {
    slug: "antisaccade",
    name: "Look Away from the Dot",
    technical: "Anti-saccade",
    short:
      "Look at the center dot. When another dot appears, look in the opposite direction.",
    duration: "~1–2 min",
    icon: "←",
    measures: "How well the eyes can resist looking at a sudden target.",
  },
  {
    slug: "gap_overlap",
    name: "Quick Reaction Dot Task",
    technical: "Gap-overlap",
    short: "Look at the center dot, then react when a new dot appears.",
    duration: "~2–3 min",
    icon: "◎",
    measures: "How the timing of the center dot affects reaction speed.",
  },
  {
    slug: "smooth_pursuit",
    name: "Follow the Moving Dot",
    technical: "Smooth pursuit",
    short: "Follow the moving dot as smoothly as you can.",
    duration: "~1–2 min",
    icon: "∿",
    measures: "How smoothly the eyes can track continuous motion.",
  },
];

export function activityBySlug(slug: string): ActivityDef | undefined {
  return ACTIVITIES.find((a) => a.slug === slug);
}

export const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/test", label: "Activities" },
  { href: "/history", label: "History" },
  { href: "/research", label: "Research" },
  { href: "/about", label: "About" },
];

// Quality label → badge variant class
export function qualityVariant(label?: string | null): string {
  switch ((label || "").toLowerCase()) {
    case "excellent":
      return "badge-green";
    case "good":
      return "badge-blue";
    case "okay":
      return "badge-amber";
    case "needs better camera setup":
      return "badge-amber";
    default:
      return "badge-gray";
  }
}

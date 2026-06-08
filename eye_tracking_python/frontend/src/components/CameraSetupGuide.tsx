"use client";

export type GuideState = "ok" | "warn" | "pending";

export interface GuideItem {
  key: string;
  label: string;
  state: GuideState;
  hint: string;
}

export default function CameraSetupGuide({ items }: { items: GuideItem[] }) {
  return (
    <ul className="checklist">
      {items.map((it) => (
        <li key={it.key}>
          <span
            className={`tick ${it.state === "ok" ? "ok" : "pending"}`}
            aria-hidden
          >
            {it.state === "ok" ? "✓" : it.state === "warn" ? "!" : "•"}
          </span>
          <div>
            <strong style={{ display: "block", fontSize: ".95rem" }}>
              {it.label}
            </strong>
            <span className="small muted">{it.hint}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

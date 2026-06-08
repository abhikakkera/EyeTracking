import Link from "next/link";
import type { ActivityDef } from "@/lib/constants";

export default function TestCard({ activity }: { activity: ActivityDef }) {
  return (
    <div className="card card-hover test-card">
      <span className="tech">{activity.technical}</span>
      <h3>{activity.name}</h3>
      <p>{activity.short}</p>
      <div className="spacer" />
      <div className="dur" aria-label="Estimated duration">
        <span aria-hidden>⏱</span> {activity.duration}
      </div>
      <Link
        className="btn btn-primary btn-block"
        href={`/setup?task=${activity.slug}`}
      >
        Start activity
      </Link>
    </div>
  );
}

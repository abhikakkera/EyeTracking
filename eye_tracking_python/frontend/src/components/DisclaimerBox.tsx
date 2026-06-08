import { DISCLAIMER } from "@/lib/constants";

export default function DisclaimerBox({
  text = DISCLAIMER,
  compact = false,
  title = "Research prototype — not a medical device",
}: {
  text?: string;
  compact?: boolean;
  title?: string;
}) {
  return (
    <div className={`disclaimer${compact ? " compact" : ""}`} role="note">
      <span className="dot" aria-hidden>
        i
      </span>
      <div>
        {!compact && <strong>{title}. </strong>}
        {text}
      </div>
    </div>
  );
}

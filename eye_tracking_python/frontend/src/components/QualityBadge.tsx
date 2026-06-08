import { qualityVariant } from "@/lib/constants";

export default function QualityBadge({ label }: { label?: string | null }) {
  if (!label) return null;
  return (
    <span className={`badge ${qualityVariant(label)}`}>
      <span className="dot-ic" aria-hidden />
      {label}
    </span>
  );
}

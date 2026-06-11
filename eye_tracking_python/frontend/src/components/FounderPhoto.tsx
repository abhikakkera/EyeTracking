"use client";

import { useState } from "react";

/**
 * Founder portrait. Drop a photo at `frontend/public/founder.jpg` and it appears
 * automatically. Until then, a clean initials placeholder is shown — so the page
 * never looks broken.
 */
export default function FounderPhoto({
  src = "/founder.jpg",
  alt,
  initials = "AK",
}: {
  src?: string;
  alt: string;
  initials?: string;
}) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div className="founder-fallback" role="img" aria-label={alt}>
        {initials}
      </div>
    );
  }

  // Plain <img> (not next/image) so a missing file degrades gracefully to the
  // initials fallback instead of throwing.
  // eslint-disable-next-line @next/next/no-img-element
  return (
    <img
      className="founder-photo"
      src={src}
      alt={alt}
      onError={() => setFailed(true)}
    />
  );
}

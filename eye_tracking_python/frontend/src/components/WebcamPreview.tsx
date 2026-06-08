"use client";

import type { RefObject } from "react";

export default function WebcamPreview({
  videoRef,
  error,
  rounded = true,
}: {
  videoRef: RefObject<HTMLVideoElement>;
  error?: string | null;
  rounded?: boolean;
}) {
  return (
    <div className="cam-preview" style={rounded ? undefined : { borderRadius: 0 }}>
      {error ? (
        <div className="cam-placeholder">{error}</div>
      ) : (
        <video ref={videoRef} playsInline muted />
      )}
    </div>
  );
}

"use client";

import { type RefObject, useEffect, useRef } from "react";

export default function WebcamPreview({
  stream,
  videoRef,
  error,
  rounded = true,
}: {
  stream?: MediaStream | null;
  videoRef?: RefObject<HTMLVideoElement>;
  error?: string | null;
  rounded?: boolean;
}) {
  const internalRef = useRef<HTMLVideoElement>(null);
  const ref = videoRef ?? internalRef;

  // When given a stream (not a ref), display it in this element. This lets the
  // preview share the same MediaStream as the hidden capture video.
  useEffect(() => {
    if (!videoRef && internalRef.current && stream) {
      internalRef.current.srcObject = stream;
      internalRef.current.play().catch(() => {});
    }
  }, [stream, videoRef]);

  return (
    <div className="cam-preview" style={rounded ? undefined : { borderRadius: 0 }}>
      {error ? (
        <div className="cam-placeholder">{error}</div>
      ) : (
        <video ref={ref} autoPlay playsInline muted />
      )}
    </div>
  );
}

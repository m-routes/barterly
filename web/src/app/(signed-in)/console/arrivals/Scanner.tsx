"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";

type Detector = { detect(source: CanvasImageSource): Promise<Array<{ rawValue: string }>> };
type DetectorClass = new (options: { formats: string[] }) => Detector;

/**
 * The camera, reading QR codes: the browser's BarcodeDetector where there is one,
 * jsQR on video frames otherwise. Calls `onCode` once per code it reads; works offline.
 */
export function Scanner({
  onCode,
  onClose,
}: {
  onCode: (text: string) => void;
  onClose: () => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const [problem, setProblem] = useState("");
  const handler = useRef(onCode);
  useEffect(() => {
    handler.current = onCode;
  });

  useEffect(() => {
    let stream: MediaStream | null = null;
    let frame = 0;
    let stopped = false;
    let last = "";
    const canvas = document.createElement("canvas");

    async function start() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setProblem("This browser can't use the camera. Use the six-digit code instead.");
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment" },
          audio: false,
        });
      } catch {
        setProblem("Allow camera access to scan, or use the six-digit code instead.");
        return;
      }
      const el = video.current;
      if (!el || stopped) return;
      el.srcObject = stream;
      await el.play().catch(() => undefined);
      const Native = (globalThis as { BarcodeDetector?: DetectorClass }).BarcodeDetector;
      const detector = Native ? new Native({ formats: ["qr_code"] }) : null;
      const { default: jsQR } = detector ? { default: null } : await import("jsqr");

      const tick = async () => {
        if (stopped || !el.videoWidth) {
          if (!stopped) frame = requestAnimationFrame(() => void tick());
          return;
        }
        let text = "";
        if (detector) {
          const found = await detector.detect(el).catch(() => []);
          text = found[0]?.rawValue ?? "";
        } else if (jsQR) {
          canvas.width = el.videoWidth;
          canvas.height = el.videoHeight;
          const ctx = canvas.getContext("2d", { willReadFrequently: true });
          ctx?.drawImage(el, 0, 0);
          const image = ctx?.getImageData(0, 0, canvas.width, canvas.height);
          text = image ? (jsQR(image.data, image.width, image.height)?.data ?? "") : "";
        }
        if (text && text !== last) {
          last = text;
          handler.current(text);
        }
        frame = requestAnimationFrame(() => void tick());
      };
      void tick();
    }

    void start();
    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  return (
    <div className="scanner stack-sm">
      {problem ? (
        <p className="form-error" role="alert">
          {problem}
        </p>
      ) : (
        <video ref={video} className="scanner__video" muted playsInline aria-label="Camera" />
      )}
      <Button variant="secondary" onClick={onClose}>
        Stop scanning
      </Button>
    </div>
  );
}

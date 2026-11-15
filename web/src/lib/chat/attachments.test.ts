import { describe, expect, it } from "vitest";

import { attachmentProblem, chatMediaKind } from "./attachments";

const file = (name: string, type: string, size = 1000) =>
  new File([new Uint8Array(size)], name, { type });

describe("chat attachments", () => {
  it("takes photos and PDFs up to 10 MB, three at a time", () => {
    expect(attachmentProblem([file("a.jpg", "image/jpeg"), file("b.pdf", "application/pdf")])).toBe(
      null,
    );
    expect(attachmentProblem([file("v.mp4", "video/mp4")])).toMatch(/photo .* or a PDF/);
    expect(attachmentProblem([file("big.png", "image/png", 11 * 1024 * 1024)])).toMatch(/10 MB/);
    expect(attachmentProblem([file("a.jpg", "image/jpeg")], 3)).toMatch(/at most 3/);
  });

  it("uploads images as photos and PDFs as documents", () => {
    expect(chatMediaKind(file("a.webp", "image/webp"))).toBe("photo");
    expect(chatMediaKind(file("b.pdf", "application/pdf"))).toBe("document");
  });
});

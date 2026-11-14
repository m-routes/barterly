import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { errorBody, jsonResponse } from "../../../test/http";

import { uploadFile, uploadProblem } from "./upload";

let network: ReturnType<typeof vi.fn>;

beforeEach(() => {
  network = vi.fn();
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const jpeg = (size = 1000) => new File([new Uint8Array(size)], "front.jpg", { type: "image/jpeg" });

describe("uploadProblem", () => {
  it("allows images under the limit and explains the rest", () => {
    expect(uploadProblem(jpeg(), "photo")).toBeNull();
    expect(uploadProblem(new File(["x"], "a.gif", { type: "image/gif" }), "photo")).toMatch(
      /JPEG, PNG or WebP/,
    );
    expect(uploadProblem(jpeg(11 * 1024 * 1024), "photo")).toMatch(/over 10 MB/);
  });
});

describe("uploadFile", () => {
  it("gets a signed URL, PUTs the file there, then confirms it", async () => {
    network
      .mockResolvedValueOnce(
        jsonResponse(201, {
          media_id: "m1",
          upload_url: "https://storage.googleapis.com/bucket/m1?sig",
          method: "PUT",
          headers: { "Content-Type": "image/jpeg" },
          expires_at: "2026-11-14T12:00:00Z",
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 200 }))
      .mockResolvedValueOnce(jsonResponse(200, { id: "m1", status: "ready" }));

    await expect(uploadFile(jpeg(), "photo")).resolves.toEqual({ mediaId: "m1" });

    const ask = network.mock.calls[0]![0] as Request;
    expect(new URL(ask.url).pathname).toBe("/api/v1/media/upload-url/");
    expect(await ask.json()).toEqual({
      kind: "photo",
      content_type: "image/jpeg",
      size_bytes: 1000,
    });
    const [url, init] = network.mock.calls[1]! as [string, RequestInit];
    expect(url).toBe("https://storage.googleapis.com/bucket/m1?sig");
    expect(init).toMatchObject({ method: "PUT", headers: { "Content-Type": "image/jpeg" } });
    const confirm = network.mock.calls[2]![0] as Request;
    expect(new URL(confirm.url).pathname).toBe("/api/v1/media/confirm/");
  });

  it("reports a failed storage upload without confirming", async () => {
    network
      .mockResolvedValueOnce(
        jsonResponse(201, {
          media_id: "m1",
          upload_url: "https://storage.example/m1",
          method: "PUT",
          headers: {},
          expires_at: "2026-11-14T12:00:00Z",
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 403 }));
    await expect(uploadFile(jpeg(), "photo")).rejects.toMatchObject({ code: "upload_failed" });
    expect(network).toHaveBeenCalledTimes(2);
  });

  it("refuses a bad file before calling the API", async () => {
    await expect(
      uploadFile(new File(["x"], "a.gif", { type: "image/gif" }), "photo"),
    ).rejects.toMatchObject({ code: "invalid_file" });
    expect(network).not.toHaveBeenCalled();
  });

  it("passes on API errors", async () => {
    network.mockResolvedValueOnce(jsonResponse(429, errorBody("throttled", "Slow down.")));
    await expect(uploadFile(jpeg(), "photo")).rejects.toMatchObject({ status: 429 });
  });
});

/**
 * Every API failure is {code, message, details} (backend apps/common/exceptions.py).
 * ApiError carries that plus the HTTP status and request id, for any failure the
 * client sees, including network errors (status 0).
 */

export type ApiErrorBody = {
  code: string;
  message: string;
  details: Record<string, unknown>;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly requestId: string | null;

  constructor(init: {
    status: number;
    code: string;
    message: string;
    details?: Record<string, unknown>;
    requestId?: string | null;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.details = init.details ?? {};
    this.requestId = init.requestId ?? null;
  }

  get isValidation(): boolean {
    return this.status === 400 && this.code === "validation_error";
  }
}

export const NETWORK_ERROR_MESSAGE = "You seem to be offline. Check your connection and try again.";
const FALLBACK_MESSAGE = "Something went wrong. Try again.";

function isErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.code === "string" && typeof v.message === "string";
}

/** Build an ApiError from a failed response and its parsed body (if any). */
export function toApiError(response: Response, body: unknown): ApiError {
  const requestId = response.headers.get("x-request-id");
  if (isErrorBody(body)) {
    const details =
      typeof body.details === "object" && body.details !== null ? body.details : undefined;
    return new ApiError({
      status: response.status,
      code: body.code,
      message: body.message,
      details,
      requestId,
    });
  }
  return new ApiError({
    status: response.status,
    code: response.status >= 500 ? "server_error" : "http_error",
    message: FALLBACK_MESSAGE,
    requestId,
  });
}

export function networkError(): ApiError {
  return new ApiError({ status: 0, code: "network_error", message: NETWORK_ERROR_MESSAGE });
}

/**
 * Field errors from a validation_error, one message per field, for form libraries.
 * `non_field_errors` is returned under the key "root".
 */
export function fieldErrors(error: ApiError): Record<string, string> {
  if (!error.isValidation) return {};
  const result: Record<string, string> = {};
  for (const [field, value] of Object.entries(error.details)) {
    const message = Array.isArray(value) ? value.find((v) => typeof v === "string") : value;
    if (typeof message !== "string") continue;
    result[field === "non_field_errors" ? "root" : field] = message;
  }
  return result;
}

/** A message safe to show a person, with the request id when there is one. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status >= 500 && error.requestId) {
      return `${error.message} (Reference: ${error.requestId})`;
    }
    return error.message;
  }
  return FALLBACK_MESSAGE;
}

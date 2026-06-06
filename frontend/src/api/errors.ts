import type { Problem, ValidationProblem, ValidationProblemError } from "@/api/types";

/**
 * Error raised when the API returns an RFC 7807 `application/problem+json`
 * response (or any non-2xx response). Carries the parsed {@link Problem} so the
 * UI can surface `code` and `detail` without leaking internals.
 */
export class ApiError extends Error {
  public readonly problem: Problem;
  public readonly status: number;

  public constructor(problem: Problem) {
    super(problem.detail ?? problem.title);
    this.name = "ApiError";
    this.problem = problem;
    this.status = problem.status;
  }

  /** Field-level validation errors when the problem is a ValidationProblem. */
  public get validationErrors(): ValidationProblemError[] {
    const candidate = this.problem as ValidationProblem;
    return candidate.errors ?? [];
  }
}

/**
 * Narrow an unknown value to a {@link Problem}.
 *
 * Validates the four RFC 7807 required members (`type`, `title`, `status`,
 * `code`) without trusting the shape, so a malformed error body cannot be
 * mistaken for a valid problem.
 */
export function isProblem(value: unknown): value is Problem {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record["type"] === "string" &&
    typeof record["title"] === "string" &&
    typeof record["status"] === "number" &&
    typeof record["code"] === "string"
  );
}

/**
 * Build a synthetic {@link Problem} for transport/parse failures that never
 * produced a server problem+json body (network down, CORS, malformed JSON).
 *
 * @param status - HTTP-like status code to attribute to the failure.
 * @param code - Machine-readable client error code.
 * @param detail - Human-readable, non-sensitive explanation.
 */
export function syntheticProblem(status: number, code: string, detail: string): Problem {
  return {
    type: "about:blank",
    title: code,
    status,
    code,
    detail,
  };
}

/**
 * Convert an arbitrary error response body into an {@link ApiError}.
 *
 * Uses the parsed problem when it conforms to RFC 7807; otherwise wraps the
 * status into a synthetic problem so callers always receive a typed error.
 *
 * @param status - HTTP status code of the failed response.
 * @param body - Parsed response body (may be a Problem, or anything).
 */
export function toApiError(status: number, body: unknown): ApiError {
  if (isProblem(body)) {
    return new ApiError(body);
  }
  return new ApiError(
    syntheticProblem(status, "UNEXPECTED_RESPONSE", "The server returned an unexpected response."),
  );
}

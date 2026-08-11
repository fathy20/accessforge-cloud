import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError } from "@/lib/apiClient";

const fetchMock = vi.fn();

function makeResponse(
  status: number,
  body: unknown,
  contentType = "application/json; charset=utf-8",
): Response {
  const responseBody = typeof body === "string" ? body : JSON.stringify(body);
  return new Response(responseBody, {
    status,
    headers: { "content-type": contentType },
  });
}

async function getApiError(action: () => Promise<unknown>): Promise<ApiError> {
  const error = await action().catch((caught) => caught);
  expect(error).toBeInstanceOf(ApiError);
  return error as ApiError;
}

describe("ApiClient error classification", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("classifies a rejected fetch as NETWORK", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("request rejected"));

    const error = await getApiError(() => ApiClient.fetch("/auth/login"));

    expect(error.kind).toBe("NETWORK");
    expect(error.status).toBeNull();
    expect(error.detail).toBeNull();
  });

  it("classifies an HTML 404 as CONFIGURATION", async () => {
    fetchMock.mockResolvedValueOnce(makeResponse(404, "<!doctype html>", "text/html; charset=utf-8"));

    const error = await getApiError(() => ApiClient.fetch("/auth/login"));

    expect(error.kind).toBe("CONFIGURATION");
    expect(error.status).toBe(404);
    expect(error.message).not.toBe("API request failed");
  });

  it("classifies a non-JSON 500 as SERVER", async () => {
    fetchMock.mockResolvedValueOnce(makeResponse(500, "Internal Server Error", "text/plain"));

    const error = await getApiError(() => ApiClient.fetch("/health"));

    expect(error.kind).toBe("SERVER");
    expect(error.status).toBe(500);
  });

  it("uses the 401 detail and clears the stored token", async () => {
    const storedValue = ["stored", "value"].join("-");
    ApiClient.setToken(storedValue);
    fetchMock.mockResolvedValueOnce(makeResponse(401, { detail: "Incorrect email or password" }));

    const error = await getApiError(() => ApiClient.fetch("/auth/login"));

    expect(error.kind).toBe("AUTHENTICATION");
    expect(error.message).toBe("Incorrect email or password");
    expect(localStorage.getItem("access_token")).toBeNull();
  });

  it("classifies a 403 as ACCOUNT_STATUS", async () => {
    fetchMock.mockResolvedValueOnce(makeResponse(403, { detail: "Account is not active" }));

    const error = await getApiError(() => ApiClient.fetch("/auth/login"));

    expect(error.kind).toBe("ACCOUNT_STATUS");
    expect(error.message).toBe("Account is not active");
  });

  it("classifies a 429 as RATE_LIMITED", async () => {
    fetchMock.mockResolvedValueOnce(makeResponse(429, { detail: "Try again later" }));

    const error = await getApiError(() => ApiClient.fetch("/auth/login"));

    expect(error.kind).toBe("RATE_LIMITED");
    expect(error.message).toBe("Try again later");
  });

  it("does not stringify an array validation detail", async () => {
    fetchMock.mockResolvedValueOnce(makeResponse(422, { detail: [{ msg: "Field required" }] }));

    const error = await getApiError(() => ApiClient.fetch("/auth/login"));

    expect(error.kind).toBe("CLIENT");
    expect(error.detail).toBeNull();
    expect(error.message).not.toContain("[object Object]");
  });

  it("resolves a successful response with its parsed body", async () => {
    const body = { status: "ok" };
    fetchMock.mockResolvedValueOnce(makeResponse(200, body));

    await expect(ApiClient.fetch("/health")).resolves.toEqual(body);
  });

  it("applies the same classification to fetchBlob", async () => {
    fetchMock.mockResolvedValueOnce(makeResponse(404, "<!doctype html>", "text/html; charset=utf-8"));
    const configurationError = await getApiError(() => ApiClient.fetchBlob("/uploads/file/download"));

    expect(configurationError.kind).toBe("CONFIGURATION");

    const storedValue = ["stored", "value"].join("-");
    ApiClient.setToken(storedValue);
    fetchMock.mockResolvedValueOnce(makeResponse(401, { detail: "Incorrect email or password" }));
    const authenticationError = await getApiError(() =>
      ApiClient.fetchBlob("/uploads/file/download"),
    );

    expect(authenticationError.kind).toBe("AUTHENTICATION");
    expect(authenticationError.message).toBe("Incorrect email or password");
    expect(localStorage.getItem("access_token")).toBeNull();
  });
});

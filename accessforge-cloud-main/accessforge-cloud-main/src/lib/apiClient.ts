export type ApiErrorKind =
  | "NETWORK"
  | "AUTHENTICATION"
  | "ACCOUNT_STATUS"
  | "RATE_LIMITED"
  | "CONFIGURATION"
  | "CLIENT"
  | "SERVER";

const DEFAULT_ERROR_MESSAGES: Record<ApiErrorKind, string> = {
  NETWORK: "Cannot reach the server. Check your connection and that the backend is running.",
  CONFIGURATION:
    "The server returned an unexpected response. The application may be misconfigured.",
  SERVER: "The server encountered an error. Please try again.",
  AUTHENTICATION: "Incorrect email or password.",
  ACCOUNT_STATUS: "This account is not active.",
  RATE_LIMITED: "Too many attempts. Please try again later.",
  CLIENT: "The request could not be completed.",
};

function getErrorMessage(kind: ApiErrorKind, detail: string | null): string {
  if (
    detail !== null &&
    (kind === "AUTHENTICATION" ||
      kind === "ACCOUNT_STATUS" ||
      kind === "RATE_LIMITED" ||
      kind === "CLIENT")
  ) {
    return detail;
  }

  return DEFAULT_ERROR_MESSAGES[kind];
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly detail: string | null;

  constructor(kind: ApiErrorKind, status: number | null, detail: string | null) {
    super(getErrorMessage(kind, detail));
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.detail = detail;
  }
}

function isJsonContentType(contentType: string | null): boolean {
  return contentType?.toLowerCase().includes("json") ?? false;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function classifyResponse(status: number, parseableJson: boolean): ApiErrorKind {
  if (!parseableJson) {
    return status >= 500 ? "SERVER" : "CONFIGURATION";
  }

  if (status === 401) return "AUTHENTICATION";
  if (status === 403) return "ACCOUNT_STATUS";
  if (status === 429) return "RATE_LIMITED";
  if (status >= 500) return "SERVER";
  return "CLIENT";
}

async function createApiError(res: Response, requestUrl: string): Promise<ApiError> {
  const contentType = res.headers.get("content-type");
  let body: unknown = null;
  let parseableJson = isJsonContentType(contentType);

  if (parseableJson) {
    try {
      body = await res.json();
    } catch {
      parseableJson = false;
    }
  }

  const kind = classifyResponse(res.status, parseableJson);
  const detail =
    parseableJson && isRecord(body) && typeof body.detail === "string" ? body.detail : null;

  if (kind === "CONFIGURATION" || kind === "SERVER") {
    console.error(
      `[ApiClient] ${kind} response url=${requestUrl} status=${res.status} content-type=${contentType ?? "none"}`,
    );
  }

  return new ApiError(kind, res.status, detail);
}

async function fetchWithNetworkError(
  requestUrl: string,
  options: RequestInit,
): Promise<Response> {
  try {
    return await fetch(requestUrl, options);
  } catch {
    throw new ApiError("NETWORK", null, null);
  }
}

export class ApiClient {
  static get API_URL() {
    return import.meta.env.VITE_API_URL || "http://localhost:8000/api";
  }
  static getToken() {
    return localStorage.getItem("access_token");
  }
  
  static setToken(token: string) {
    localStorage.setItem("access_token", token);
  }
  
  static clearToken() {
    localStorage.removeItem("access_token");
  }

  static async fetch<T = any>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const token = this.getToken();
    const headers = new Headers(options.headers || {});
    
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    
    if (!options.body || !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }

    const requestUrl = `${this.API_URL}${endpoint}`;
    const res = await fetchWithNetworkError(requestUrl, {
      ...options,
      headers
    });

    if (!res.ok) {
      if (res.status === 401) {
        this.clearToken();
        // Redirect to login could go here
      }
      throw await createApiError(res, requestUrl);
    }

    return res.json();
  }

  static async fetchBlob(
    endpoint: string,
    options: RequestInit = {},
  ): Promise<{ blob: Blob; filename: string | null }> {
    const token = this.getToken();
    const headers = new Headers(options.headers || {});

    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    const requestUrl = `${this.API_URL}${endpoint}`;
    const res = await fetchWithNetworkError(requestUrl, {
      ...options,
      headers,
    });

    if (!res.ok) {
      if (res.status === 401) {
        this.clearToken();
      }
      throw await createApiError(res, requestUrl);
    }

    const contentDisposition = res.headers.get("Content-Disposition");
    const filenameMatch = contentDisposition?.match(
      /filename\*=UTF-8''([^;]+)|filename=(?:"([^"]+)"|([^;]+))/i,
    );
    const encodedFilename = filenameMatch?.[1] || filenameMatch?.[2] || filenameMatch?.[3];
    let filename: string | null = null;
    if (encodedFilename) {
      try {
        filename = decodeURIComponent(encodedFilename.trim());
      } catch {
        filename = encodedFilename.trim();
      }
    }

    return { blob: await res.blob(), filename };
  }
}

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

    const res = await fetch(`${this.API_URL}${endpoint}`, {
      ...options,
      headers
    });

    if (!res.ok) {
      if (res.status === 401) {
        this.clearToken();
        // Redirect to login could go here
      }
      const error = await res.json().catch(() => ({}));
      throw new Error(error.detail || "API request failed");
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

    const res = await fetch(`${this.API_URL}${endpoint}`, {
      ...options,
      headers,
    });

    if (!res.ok) {
      if (res.status === 401) {
        this.clearToken();
      }
      const error = await res.json().catch(() => ({}));
      throw new Error(error.detail || "API request failed");
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

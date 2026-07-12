const API_URL = "http://localhost:8000/api";

export class ApiClient {
  static getToken() {
    return localStorage.getItem("access_token");
  }
  
  static setToken(token: string) {
    localStorage.setItem("access_token", token);
  }
  
  static clearToken() {
    localStorage.removeItem("access_token");
  }

  static async fetch(endpoint: string, options: RequestInit = {}) {
    const token = this.getToken();
    const headers = new Headers(options.headers || {});
    
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    
    if (!options.body || !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }

    const res = await fetch(`${API_URL}${endpoint}`, {
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
}

import { useEffect, useState } from "react";
import { ApiClient } from "@/lib/apiClient";

export interface User {
  id: string;
  email: string;
  full_name: string;
  roles: string[];
}

export interface AuthState {
  session: { access_token: string } | null;
  user: User | null;
  loading: boolean;
}

export function useAuth(): AuthState {
  const [state, setState] = useState<AuthState>({ session: null, user: null, loading: true });

  useEffect(() => {
    const token = ApiClient.getToken();
    if (!token) {
      setState({ session: null, user: null, loading: false });
      return;
    }

    ApiClient.fetch("/auth/me")
      .then((user) => {
        setState({ session: { access_token: token }, user, loading: false });
      })
      .catch(() => {
        ApiClient.clearToken();
        setState({ session: null, user: null, loading: false });
      });
  }, []);

  return state;
}

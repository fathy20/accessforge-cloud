import { queryOptions, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
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

/**
 * One definition of the "who am I" query so the route guard and the hooks
 * share the same cache entry: a guard hit warms the cache and the hooks read
 * it without a second request per navigation.
 */
export const authMeQuery = queryOptions({
  queryKey: ["auth-me"],
  queryFn: () => ApiClient.fetch<User>("/auth/me"),
  retry: false,
  staleTime: 5 * 60_000,
});

export function useAuth(): AuthState {
  const queryClient = useQueryClient();
  const token = typeof window !== "undefined" ? ApiClient.getToken() : null;

  const {
    data: user,
    isLoading,
    isError,
  } = useQuery({
    ...authMeQuery,
    enabled: !!token,
  });

  // Signing out is a side effect, so it belongs in an effect rather than in
  // the render body where it re-ran on every render of every consumer.
  useEffect(() => {
    if (!isError) return;
    ApiClient.clearToken();
    queryClient.removeQueries({ queryKey: authMeQuery.queryKey });
  }, [isError, queryClient]);

  return {
    session: token ? { access_token: token } : null,
    user: user ?? null,
    loading: isLoading,
  };
}

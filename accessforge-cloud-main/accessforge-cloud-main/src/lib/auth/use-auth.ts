import { useQuery, useQueryClient } from "@tanstack/react-query";
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
  const queryClient = useQueryClient();
  
  const token = typeof window !== "undefined" ? ApiClient.getToken() : null;

  const { data: user, isLoading, isError } = useQuery({
    queryKey: ["auth-me"],
    queryFn: async () => {
      return await ApiClient.fetch("/auth/me");
    },
    enabled: !!token,
    retry: false,
    staleTime: 1000 * 60 * 5, // 5 minutes cache
  });

  // Handle auto logout on error
  if (isError) {
    ApiClient.clearToken();
    queryClient.setQueryData(["auth-me"], null);
  }

  return {
    session: token ? { access_token: token } : null,
    user: user || null,
    loading: isLoading,
  };
}

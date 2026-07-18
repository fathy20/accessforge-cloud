import { ApiClient } from "@/lib/apiClient";

export async function listUsers() {
  return await ApiClient.fetch("/admin/users");
}

export async function setUserStatus(data: { data: { userId: string; status: string } } | { userId: string; status: string }) {
  const payload = "data" in data ? data.data : data;
  return await ApiClient.fetch(`/admin/users/${payload.userId}/status`, {
    method: "POST",
    body: JSON.stringify({ status: payload.status }),
  });
}

export async function setUserRole(data: { data: { userId: string; role: string } } | { userId: string; role: string }) {
  const payload = "data" in data ? data.data : data;
  return await ApiClient.fetch(`/admin/users/${payload.userId}/roles`, {
    method: "POST",
    body: JSON.stringify({ roles: [payload.role] }),
  });
}

export async function deleteUser(data: { data: { userId: string } } | { userId: string }) {
  const payload = "data" in data ? data.data : data;
  return await ApiClient.fetch(`/admin/users/${payload.userId}`, {
    method: "DELETE",
  });
}

export async function sendPasswordReset(data: { data: { email: string; redirectTo?: string } } | { email: string; redirectTo?: string }) {
  const payload = "data" in data ? data.data : data;
  return await ApiClient.fetch("/admin/users/reset-password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function inviteUser(data: { data: { email: string; role: string; redirectTo?: string } } | { email: string; role: string; redirectTo?: string }) {
  const payload = "data" in data ? data.data : data;
  return await ApiClient.fetch("/admin/invitations", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listInvitations() {
  return await ApiClient.fetch("/admin/invitations");
}

export async function revokeInvitation(data: { data: { id: string } } | { id: string }) {
  const payload = "data" in data ? data.data : data;
  return await ApiClient.fetch(`/admin/invitations/${payload.id}`, {
    method: "DELETE",
  });
}

export async function listMyNotifications() {
  return await ApiClient.fetch("/notifications");
}

export async function markNotificationRead(data: { data: { id: string } } | { id: string }) {
  const payload = "data" in data ? data.data : data;
  return await ApiClient.fetch(`/notifications/${payload.id}/read`, {
    method: "POST",
  });
}

export async function markAllNotificationsRead() {
  return await ApiClient.fetch("/notifications/read-all", {
    method: "POST",
  });
}

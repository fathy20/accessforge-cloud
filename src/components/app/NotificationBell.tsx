import { useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { Bell, Check } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/lib/auth/use-auth";
import { listMyNotifications, markNotificationRead, markAllNotificationsRead } from "@/lib/admin.functions";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { formatDistanceToNow } from "date-fns";

export function NotificationBell() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const list = useServerFn(listMyNotifications);
  const markRead = useServerFn(markNotificationRead);
  const markAll = useServerFn(markAllNotificationsRead);
  const [open, setOpen] = useState(false);

  const { data: notifications = [] } = useQuery({
    queryKey: ["my-notifications"],
    queryFn: () => list(),
    enabled: !!user,
    refetchInterval: 60_000,
  });

  useEffect(() => {
    if (!user) return;
    const channel = supabase
      .channel(`notifs-${user.id}`)
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "notifications", filter: `user_id=eq.${user.id}` },
        () => qc.invalidateQueries({ queryKey: ["my-notifications"] }),
      )
      .subscribe();
    return () => { supabase.removeChannel(channel); };
  }, [user, qc]);

  const unread = notifications.filter((n) => !n.read_at).length;

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative rounded-full">
          <Bell className="size-4" />
          {unread > 0 && (
            <Badge className="absolute -top-0.5 -right-0.5 h-4 min-w-4 px-1 text-[10px] flex items-center justify-center bg-primary text-primary-foreground border-0">
              {unread > 9 ? "9+" : unread}
            </Badge>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 p-0 max-h-[70vh] overflow-y-auto">
        <div className="flex items-center justify-between p-3 border-b border-border">
          <p className="font-semibold text-sm">Notifications</p>
          {unread > 0 && (
            <button
              onClick={async () => {
                await markAll();
                qc.invalidateQueries({ queryKey: ["my-notifications"] });
              }}
              className="text-xs text-primary hover:underline"
            >
              Mark all read
            </button>
          )}
        </div>
        {notifications.length === 0 ? (
          <div className="p-6 text-sm text-muted-foreground text-center">No notifications yet.</div>
        ) : (
          <div className="divide-y divide-border">
            {notifications.map((n) => {
              const body = (
                <>
                  <div className="flex items-start justify-between gap-2">
                    <p className={`text-sm ${n.read_at ? "text-muted-foreground" : "font-medium"}`}>
                      {n.title}
                    </p>
                    {!n.read_at && <span className="size-1.5 rounded-full bg-primary mt-1.5 shrink-0" />}
                  </div>
                  {n.body && <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{n.body}</p>}
                  <p className="text-[10px] text-muted-foreground mt-1">
                    {formatDistanceToNow(new Date(n.created_at), { addSuffix: true })}
                  </p>
                </>
              );
              const onClick = async () => {
                if (!n.read_at) {
                  await markRead({ data: { id: n.id } });
                  qc.invalidateQueries({ queryKey: ["my-notifications"] });
                }
                setOpen(false);
              };
              return n.link ? (
                <Link key={n.id} to={n.link} onClick={onClick} className="block p-3 hover:bg-accent/50 transition-colors">
                  {body}
                </Link>
              ) : (
                <button key={n.id} onClick={onClick} className="w-full text-left p-3 hover:bg-accent/50 transition-colors">
                  {body}
                </button>
              );
            })}
          </div>
        )}
        {notifications.length > 0 && unread === 0 && (
          <div className="p-3 border-t border-border flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
            <Check className="size-3" /> All caught up
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

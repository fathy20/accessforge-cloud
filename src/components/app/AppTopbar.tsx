import { useNavigate } from "@tanstack/react-router";
import { LogOut, User as UserIcon, Search as SearchIcon, Languages } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/lib/auth/use-auth";
import { usePermissions } from "@/lib/auth/use-permissions";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";

export function AppTopbar() {
  const { user } = useAuth();
  const perms = usePermissions();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { t, lang, setLang } = useI18n();


  const initials = (user?.user_metadata?.full_name as string | undefined)
    ?.split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase() ?? user?.email?.[0]?.toUpperCase() ?? "U";

  const signOut = async () => {
    await qc.cancelQueries();
    qc.clear();
    await supabase.auth.signOut();
    navigate({ to: "/auth", replace: true });
  };

  const topRole = perms.roles[0] ?? "guest";

  return (
    <header className="h-14 border-b border-border bg-card/40 backdrop-blur flex items-center gap-4 px-6">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const q = (new FormData(e.currentTarget).get("q") as string)?.trim();
          navigate({ to: "/search", search: q ? { q } : undefined });
        }}
        className="hidden md:flex flex-1 max-w-md relative"
      >
        <SearchIcon className="size-4 absolute start-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input name="q" placeholder={t("top.search_placeholder")} className="ps-9 h-9" />
      </form>

      <div className="ms-auto flex items-center gap-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setLang(lang === "ar" ? "en" : "ar")}
          className="gap-2"
          title={t("top.language")}
        >
          <Languages className="size-4" />
          <span className="text-xs font-medium">{lang === "ar" ? "EN" : "ع"}</span>
        </Button>
        <Badge variant="secondary" className="capitalize">
          {topRole.replace("_", " ")}
        </Badge>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="rounded-full">
              <Avatar className="size-8">
                <AvatarFallback className="bg-primary/15 text-primary text-xs font-semibold">
                  {initials}
                </AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel className="flex flex-col">
              <span className="font-medium">
                {(user?.user_metadata?.full_name as string | undefined) ?? t("top.signed_in")}
              </span>
              <span className="text-xs text-muted-foreground truncate">{user?.email}</span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate({ to: "/profile" })}>
              <UserIcon className="size-4" /> {t("nav.profile")}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={signOut} className="text-destructive focus:text-destructive">
              <LogOut className="size-4" /> {t("top.signout")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}

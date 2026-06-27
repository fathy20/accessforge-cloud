import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Upload as UploadIcon, FileText, Trash2, Download, Loader2 } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/lib/auth/use-auth";
import { useI18n } from "@/lib/i18n";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { detectKind, formatBytes, sanitizeName, sha256Hex } from "@/lib/uploads/helpers";

export const Route = createFileRoute("/_authenticated/uploads")({
  head: () => ({ meta: [{ title: "Uploads · REDSEA" }] }),
  component: UploadsPage,
});

const MAX_BYTES = 100 * 1024 * 1024; // 100MB

function UploadsPage() {
  const { user } = useAuth();
  const { lang } = useI18n();
  const ar = lang === "ar";
  const qc = useQueryClient();
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: uploads = [], isLoading } = useQuery({
    queryKey: ["uploads", user?.id],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("uploads")
        .select("id, original_name, kind, size_bytes, sha256, storage_path, created_at, mime_type")
        .order("created_at", { ascending: false })
        .limit(200);
      if (error) throw error;
      return data;
    },
    enabled: !!user,
  });

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    if (!user) return;
    const list = Array.from(files);
    if (!list.length) return;
    setBusy(true);
    let ok = 0, dup = 0, fail = 0;
    for (const file of list) {
      try {
        if (file.size > MAX_BYTES) {
          toast.error(`${file.name}: > 100MB`);
          fail++; continue;
        }
        const hash = await sha256Hex(file);
        const kind = detectKind(file);
        const path = `${user.id}/unassigned/${hash}-${sanitizeName(file.name)}`;
        const { error: upErr } = await supabase.storage
          .from("uploads")
          .upload(path, file, { cacheControl: "3600", upsert: false, contentType: file.type || undefined });
        if (upErr) {
          if (upErr.message?.toLowerCase().includes("already exists")) { dup++; continue; }
          throw upErr;
        }
        const { error: insErr } = await supabase.from("uploads").insert({
          uploader_id: user.id,
          original_name: file.name,
          storage_path: path,
          kind,
          mime_type: file.type || null,
          size_bytes: file.size,
          sha256: hash,
        });
        if (insErr) throw insErr;
        ok++;
      } catch (e) {
        console.error(e);
        fail++;
        toast.error(`${file.name}: ${(e as Error).message}`);
      }
    }
    setBusy(false);
    if (ok) toast.success(ar ? `تم رفع ${ok} ملف` : `Uploaded ${ok} file(s)`);
    if (dup) toast.info(ar ? `${dup} مكرر` : `${dup} duplicate(s) skipped`);
    if (fail) toast.error(ar ? `فشل ${fail}` : `${fail} failed`);
    qc.invalidateQueries({ queryKey: ["uploads"] });
  }, [user, qc, ar]);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    if (e.dataTransfer.files?.length) handleFiles(e.dataTransfer.files);
  };

  const remove = async (id: string, path: string) => {
    if (!confirm(ar ? "حذف الملف؟" : "Delete file?")) return;
    const { error: sErr } = await supabase.storage.from("uploads").remove([path]);
    if (sErr) { toast.error(sErr.message); return; }
    const { error: dErr } = await supabase.from("uploads").delete().eq("id", id);
    if (dErr) { toast.error(dErr.message); return; }
    toast.success(ar ? "تم الحذف" : "Deleted");
    qc.invalidateQueries({ queryKey: ["uploads"] });
  };

  const download = async (path: string, name: string) => {
    const { data, error } = await supabase.storage.from("uploads").createSignedUrl(path, 60);
    if (error || !data) { toast.error(error?.message ?? "Error"); return; }
    const a = document.createElement("a");
    a.href = data.signedUrl; a.download = name; a.click();
  };

  const filtered = uploads.filter((u) =>
    !filter || u.original_name.toLowerCase().includes(filter.toLowerCase()),
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{ar ? "الملفات" : "Uploads"}</h1>
          <p className="text-sm text-muted-foreground">
            {ar ? "اسحب وأفلت ملفات PDF / Excel / DOCX. يتم التحقق من التكرار تلقائياً عبر SHA-256." : "Drag & drop PDF / Excel / DOCX. Duplicates detected via SHA-256."}
          </p>
        </div>
        <Input
          placeholder={ar ? "تصفية بالاسم…" : "Filter by name…"}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-full sm:w-72"
        />
      </div>

      <Card
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`border-2 border-dashed transition-colors ${dragging ? "border-primary bg-primary/5" : "border-border"}`}
      >
        <CardContent className="p-10 grid place-items-center text-center gap-3">
          {busy ? <Loader2 className="size-10 animate-spin text-primary" /> : <UploadIcon className="size-10 text-primary" />}
          <p className="text-sm text-muted-foreground">
            {ar ? "اسحب الملفات هنا أو" : "Drop files here or"}
          </p>
          <Button onClick={() => fileInputRef.current?.click()} disabled={busy}>
            {ar ? "اختر ملفات" : "Choose files"}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            hidden
            onChange={(e) => e.target.files && handleFiles(e.target.files)}
          />
          <p className="text-xs text-muted-foreground">PDF · XLSX · DOCX · CSV — max 100MB</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            {ar ? `الملفات (${filtered.length})` : `Files (${filtered.length})`}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-10 grid place-items-center"><Loader2 className="size-5 animate-spin text-muted-foreground" /></div>
          ) : filtered.length === 0 ? (
            <div className="p-10 text-center text-sm text-muted-foreground">
              {ar ? "لا توجد ملفات بعد." : "No files yet."}
            </div>
          ) : (
            <div className="divide-y divide-border">
              {filtered.map((u) => (
                <div key={u.id} className="flex items-center gap-3 px-4 py-3 hover:bg-muted/30">
                  <FileText className="size-5 text-muted-foreground shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{u.original_name}</p>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                      <Badge variant="secondary" className="text-[10px] uppercase">{u.kind}</Badge>
                      <span>{formatBytes(u.size_bytes)}</span>
                      <span>·</span>
                      <span>{new Date(u.created_at).toLocaleString()}</span>
                    </div>
                  </div>
                  <Button variant="ghost" size="icon" onClick={() => download(u.storage_path, u.original_name)} title={ar ? "تنزيل" : "Download"}>
                    <Download className="size-4" />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => remove(u.id, u.storage_path)} title={ar ? "حذف" : "Delete"}>
                    <Trash2 className="size-4 text-destructive" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

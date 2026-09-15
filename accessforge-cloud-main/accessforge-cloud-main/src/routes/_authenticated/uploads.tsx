import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Upload as UploadIcon, Search, Trash2, Download, Loader2 } from "lucide-react";
import { ApiClient } from "@/lib/apiClient";
import { useAuth } from "@/lib/auth/use-auth";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { downloadAuthenticated, formatBytes } from "@/lib/uploads/helpers";

export const Route = createFileRoute("/_authenticated/uploads")({
  head: () => ({ meta: [{ title: "Uploads · REDSEA" }] }),
  component: UploadsPage,
});

const MAX_BYTES = 100 * 1024 * 1024; // 100MB

const ACCEPTED = ["PDF", "XLSX", "DOCX", "CSV"] as const;

/**
 * Each accepted type gets its own tinted chip. These come from the status-*
 * families rather than the on-solid *-foreground tokens, because the chip is a
 * tint that lets the card show through — the on-solid inks are near-invisible
 * against it in both themes.
 */
const TYPE_TONE: Record<string, string> = {
  pdf: "bg-status-danger-background text-status-danger-foreground border-status-danger-border",
  xlsx: "bg-status-success-background text-status-success-foreground border-status-success-border",
  xls: "bg-status-success-background text-status-success-foreground border-status-success-border",
  csv: "bg-status-warning-background text-status-warning-foreground border-status-warning-border",
  docx: "bg-status-info-background text-status-info-foreground border-status-info-border",
  doc: "bg-status-info-background text-status-info-foreground border-status-info-border",
};
const TYPE_TONE_FALLBACK =
  "bg-status-neutral-background text-status-neutral-foreground border-status-neutral-border";

function extensionOf(name: string, kind?: string) {
  const fromName = name.includes(".") ? name.split(".").pop() : "";
  return (fromName || kind || "file").toLowerCase();
}

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
      return await ApiClient.fetch("/uploads");
    },
    enabled: !!user,
  });

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    if (!user) return;
    const list = Array.from(files);
    if (!list.length) return;
    setBusy(true);
    let ok = 0, fail = 0;
    for (const file of list) {
      try {
        if (file.size > MAX_BYTES) {
          toast.error(`${file.name}: > 100MB`);
          fail++; continue;
        }
        const formData = new FormData();
        formData.append("files", file);
        await ApiClient.fetch("/uploads", {
          method: "POST",
          body: formData,
        });
        ok++;
      } catch (e) {
        console.error(e);
        fail++;
        toast.error(`${file.name}: ${(e as Error).message}`);
      }
    }
    setBusy(false);
    if (ok) toast.success(ar ? `تم رفع ${ok} ملف` : `Uploaded ${ok} file(s)`);
    if (fail) toast.error(ar ? `فشل ${fail}` : `${fail} failed`);
    qc.invalidateQueries({ queryKey: ["uploads"] });
  }, [user, qc, ar]);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    if (e.dataTransfer.files?.length) handleFiles(e.dataTransfer.files);
  };

  const remove = async (id: string) => {
    if (!confirm(ar ? "حذف الملف؟" : "Delete file?")) return;
    try {
      await ApiClient.fetch(`/uploads/${id}`, { method: "DELETE" });
      toast.success(ar ? "تم الحذف" : "Deleted");
      qc.invalidateQueries({ queryKey: ["uploads"] });
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  const download = async (id: string, name: string) => {
    try {
      // window.open cannot carry the Bearer token; fetch with auth instead.
      await downloadAuthenticated(`/uploads/${id}/download`, name);
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  const filtered = uploads.filter((u: any) =>
    !filter || u.original_name.toLowerCase().includes(filter.toLowerCase()),
  );

  /**
   * Real duplicate detection, not a decorative badge: the backend already
   * stores a SHA-256 per upload, so any row whose hash was seen earlier in the
   * list is a genuine byte-for-byte repeat. Rows with no hash are never marked.
   */
  const duplicateIds = useMemo(() => {
    const seen = new Set<string>();
    const dupes = new Set<string>();
    for (const u of uploads as any[]) {
      if (!u.sha256) continue;
      if (seen.has(u.sha256)) dupes.add(u.id);
      else seen.add(u.sha256);
    }
    return dupes;
  }, [uploads]);

  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-primary">
          {ar ? "المستندات / الملفات" : "Documents / Uploads"}
        </p>
        <h1 className="text-4xl font-bold tracking-tight">{ar ? "الملفات" : "Uploads"}</h1>
        <p className="max-w-xl text-sm leading-relaxed text-muted-foreground">
          {ar
            ? "اسحب وأفلت ملفات PDF أو Excel أو Word. يتم اكتشاف التكرار تلقائياً عبر SHA-256."
            : "Drag & drop PDF, Excel or Word files. Duplicates are detected automatically via SHA-256."}
        </p>
      </header>

      {/* Dropzone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={
          "rounded-2xl border-2 border-dashed px-6 py-14 text-center " +
          "duration-[var(--motion-duration-base)] ease-[var(--motion-ease-standard)] " +
          "transition-[border-color,background-color] " +
          (dragging ? "border-primary bg-[var(--brand-subtle)]" : "border-border bg-card/40")
        }
      >
        <div
          className="mx-auto grid size-16 place-items-center rounded-2xl bg-primary text-primary-foreground"
          style={{ boxShadow: "var(--shadow-glow)" }}
        >
          {busy
            ? <Loader2 className="size-7 animate-spin" aria-hidden="true" />
            : <UploadIcon className="size-7" aria-hidden="true" />}
        </div>

        <p className="mt-6 text-2xl font-semibold tracking-tight">
          {ar ? "أفلت الملفات هنا" : "Drop files here"}
        </p>

        <p className="mt-1.5 text-sm text-muted-foreground">
          {ar ? "أو " : "or "}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={busy}
            className="font-medium text-primary underline underline-offset-4 hover:brightness-110 disabled:opacity-50"
          >
            {ar ? "تصفّح من جهازك" : "browse from your computer"}
          </button>
        </p>

        <input
          ref={fileInputRef}
          type="file"
          multiple
          hidden
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
        />

        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
          {ACCEPTED.map((ext) => (
            <span
              key={ext}
              className="rounded-full border border-border bg-muted/50 px-3 py-1 text-[11px] font-semibold tracking-wide text-muted-foreground"
            >
              {ext}
            </span>
          ))}
          <span className="ms-1 text-xs text-muted-foreground">
            {ar ? "بحد أقصى 100 ميجابايت" : "max 100 MB"}
          </span>
        </div>
      </div>

      {/* Files */}
      <section className="overflow-hidden rounded-2xl border border-border bg-card">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
          <h2 className="text-lg font-semibold">
            {ar ? "الملفات" : "Files"}{" "}
            <span className="text-muted-foreground">({filtered.length})</span>
          </h2>
          <div className="relative w-full sm:w-72">
            <Search
              className="pointer-events-none absolute inset-y-0 start-3 my-auto size-3.5 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              placeholder={ar ? "تصفية بالاسم…" : "Filter by name…"}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="ps-9"
            />
          </div>
        </div>

        {isLoading ? (
          <div className="grid place-items-center p-14">
            <Loader2 className="size-5 animate-spin text-muted-foreground" aria-hidden="true" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-14 text-center text-sm text-muted-foreground">
            {ar ? "لا توجد ملفات بعد." : "No files yet."}
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {filtered.map((u: any) => {
              const ext = extensionOf(u.original_name, u.kind);
              const tone = TYPE_TONE[ext] ?? TYPE_TONE_FALLBACK;
              const isDuplicate = duplicateIds.has(u.id);
              return (
                <li
                  key={u.id}
                  className="flex items-center gap-4 px-5 py-4 duration-[var(--motion-duration-fast)] transition-colors hover:bg-[var(--interactive-hover)]"
                >
                  <span
                    aria-hidden="true"
                    className={`grid size-11 shrink-0 place-items-center rounded-xl border text-[10px] font-bold uppercase ${tone}`}
                  >
                    {ext.slice(0, 4)}
                  </span>

                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold">{u.original_name}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {new Date(u.created_at).toLocaleString(ar ? "ar" : "en-GB", {
                        year: "numeric", month: "short", day: "numeric",
                        hour: "2-digit", minute: "2-digit",
                      })}
                    </p>
                  </div>

                  {isDuplicate && (
                    <span
                      title={ar ? "نفس بصمة SHA-256 لملف سابق" : "Same SHA-256 as an earlier file"}
                      className="hidden shrink-0 rounded-md border border-status-warning-border bg-status-warning-background px-2.5 py-1 text-[11px] font-semibold text-status-warning-foreground sm:inline-block"
                    >
                      {ar ? "مكرر" : "Duplicate"}
                    </span>
                  )}

                  {/* dir="ltr": "4.2 MB" is a number followed by a Latin unit,
                      which bidi reorders to "MB 4.2" inside an RTL row. */}
                  <span
                    dir="ltr"
                    className="shrink-0 text-sm tabular-nums text-muted-foreground"
                  >
                    {formatBytes(u.size_bytes)}
                  </span>

                  <div className="flex shrink-0 items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => download(u.id, u.original_name)}
                      title={ar ? "تنزيل" : "Download"}
                    >
                      <Download className="size-4" aria-hidden="true" />
                      <span className="sr-only">{ar ? "تنزيل" : "Download"}</span>
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => remove(u.id)}
                      className="gap-1.5"
                    >
                      <Trash2 className="size-3.5" aria-hidden="true" />
                      {ar ? "إزالة" : "Remove"}
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

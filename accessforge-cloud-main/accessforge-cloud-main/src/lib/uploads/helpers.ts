export type UploadKind = "pdf" | "excel" | "docx" | "csv" | "image" | "other";

export async function sha256Hex(file: File): Promise<string> {
  const buf = await file.arrayBuffer();
  const hash = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function detectKind(file: File): UploadKind {
  const n = file.name.toLowerCase();
  const t = file.type.toLowerCase();
  if (n.endsWith(".pdf") || t === "application/pdf") return "pdf";
  if (n.endsWith(".xlsx") || n.endsWith(".xls") || t.includes("spreadsheet") || t.includes("excel")) return "excel";
  if (n.endsWith(".docx") || n.endsWith(".doc") || t.includes("word")) return "docx";
  if (n.endsWith(".csv") || t === "text/csv") return "csv";
  if (t.startsWith("image/")) return "image";
  return "other";
}

export function formatBytes(n: number | null | undefined): string {
  if (!n && n !== 0) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

export function sanitizeName(name: string): string {
  return name.replace(/[^\w.\-]+/g, "_").slice(0, 180);
}

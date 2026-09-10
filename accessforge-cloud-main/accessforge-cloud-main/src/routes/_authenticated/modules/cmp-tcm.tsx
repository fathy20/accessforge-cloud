import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ModuleRunner } from "@/components/app/ModuleRunner";
import { ApiClient } from "@/lib/apiClient";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useI18n } from "@/lib/i18n";
import { MODULE_ICONS } from "@/lib/modules/icons";

export const Route = createFileRoute("/_authenticated/modules/cmp-tcm")({
  head: () => ({ meta: [{ title: "CMP / TCM · REDSEA" }] }),
  component: CmpTcmPage,
});

/**
 * Fallback list, shown only until the selected workbook can speak for itself.
 *
 * The desktop app never uses a fixed list: picking the MPD RSD Excel
 * repopulates the Check combo from the distinct values in column 24 of that
 * workbook (app2.py `_pick_mpd_rsd_excel` -> `_refresh_available_checks`). We
 * keep these codes for the moment before an Excel is selected, and for a
 * workbook the server could not read, so the control is never empty.
 */
const CHECK_OPTIONS = [
  ...Array.from({ length: 11 }, (_, i) => `A${i + 1}`),
  ...Array.from({ length: 6 }, (_, i) => `C${i + 1}`),
  "120DY", "240DY", "12MO", "16MO", "2000FC"
];

// Must match the ModuleRunner props below: the uploads query key is derived
// from them, so sharing the constant shares the react-query cache entry
// instead of issuing a second listing request.
const ACCEPTED_KINDS: Array<"pdf" | "excel"> = ["pdf", "excel"];

type UploadRow = { id: string; kind: string };

function CmpTcmPage() {
  const { lang } = useI18n();
  const ar = lang === "ar";

  const [checkCode, setCheckCode] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const onSelectionChange = useCallback((ids: string[]) => {
    setSelectedIds((previous) =>
      previous.length === ids.length && previous.every((id, index) => id === ids[index])
        ? previous
        : ids,
    );
  }, []);

  // Same key and body as ModuleRunner's own listing, so this reads the cached
  // rows rather than fetching a second copy. Only needed once something is
  // selected -- which also means it never runs for a user ModuleRunner has
  // already refused on permissions.
  const { data: files = [] } = useQuery({
    queryKey: ["uploads", "kinds", ACCEPTED_KINDS.join(",")],
    enabled: selectedIds.length > 0,
    queryFn: async () => {
      const data = await ApiClient.fetch<UploadRow[]>("/uploads");
      return data.filter((u) => (ACCEPTED_KINDS as string[]).includes(u.kind));
    },
  });

  // The check codes come out of one workbook. With no spreadsheet selected, or
  // several, there is no single source to read, so the fallback list stands.
  const excelUploadId = useMemo(() => {
    const excelIds = selectedIds.filter((id) =>
      files.some((file) => file.id === id && file.kind === "excel"),
    );
    return excelIds.length === 1 ? excelIds[0] : null;
  }, [selectedIds, files]);

  const { data: workbookCodes = [], isFetching: loadingCodes } = useQuery({
    queryKey: ["upload-check-codes", excelUploadId],
    enabled: Boolean(excelUploadId),
    queryFn: async () => {
      const data = await ApiClient.fetch(`/uploads/${excelUploadId}/check-codes`);
      return Array.isArray(data?.codes) ? (data.codes as string[]) : [];
    },
  });

  const fromWorkbook = workbookCodes.length > 0;
  const options = useMemo(
    () => (fromWorkbook ? workbookCodes : CHECK_OPTIONS),
    [fromWorkbook, workbookCodes],
  );

  // Submitting a check the workbook does not contain produces zero task cards
  // and no explanation, so drop a stale choice instead of carrying it over.
  useEffect(() => {
    if (checkCode && !options.includes(checkCode)) setCheckCode("");
  }, [options, checkCode]);

  const sourceHint = loadingCodes
    ? ar
      ? "جارٍ قراءة الفحوصات من الملف..."
      : "Reading checks from the workbook..."
    : fromWorkbook
      ? ar
        ? `${options.length} فحص من ملف Excel المحدد`
        : `${options.length} check(s) found in the selected workbook`
      : ar
        ? "قائمة افتراضية — اختر ملف Excel واحد لقراءة الفحوصات منه"
        : "Default list - select one Excel file to read its checks";

  const extraControls = (
    <Card className="border-primary/20 bg-primary/5">
      <CardContent className="p-4">
        <div className="space-y-1.5 max-w-sm">
          <Label>{ar ? "رمز الفحص (Check Code)" : "Check Code"}</Label>
          <Select value={checkCode} onValueChange={setCheckCode}>
            <SelectTrigger className="bg-background">
              <SelectValue placeholder={ar ? "اختر الفحص..." : "Select check (optional)..."} />
            </SelectTrigger>
            <SelectContent>
              {options.map((code) => (
                <SelectItem key={code} value={code}>
                  {code}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">{sourceHint}</p>
        </div>
      </CardContent>
    </Card>
  );

  return (
    <ModuleRunner
      moduleKey="cmp_tcm"
      title="CMP / TCM Tasks"
      titleAr="CMP / TCM Tasks"
      description="Extract TCM tasks using an MPD RSD Excel and index them."
      descriptionAr="استخراج مهام TCM باستخدام ملف Excel MPD RSD وفهرستها."
      icon={MODULE_ICONS.cmp_tcm}
      acceptedKinds={ACCEPTED_KINDS}
      minFiles={1}
      extraControls={extraControls}
      extraInput={{ check: checkCode }}
      onSelectionChange={onSelectionChange}
    />
  );
}

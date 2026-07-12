import { createFileRoute } from "@tanstack/react-router";
import { FileSearch, Search, Loader2, Table2, FileText, Hash, FileJson, ArrowUpDown, Download } from "lucide-react";
import { ModuleRunner } from "@/components/app/ModuleRunner";
import { useState, useMemo } from "react";
import { ApiClient } from "@/lib/apiClient";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useI18n } from "@/lib/i18n";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

export const Route = createFileRoute("/_authenticated/modules/task-extractor")({
  head: () => ({ meta: [{ title: "Task Extractor · REDSEA" }] }),
  component: TaskExtractorPage,
});

function TaskExtractorPage() {
  const { lang } = useI18n();
  const ar = lang === "ar";
  const [taskCode, setTaskCode] = useState("");

  return (
    <div className="space-y-6">
      <Card className="border-t-4 border-t-primary shadow-sm bg-card/50">
        <CardContent className="pt-6">
          <div className="grid gap-3">
            <Label htmlFor="task_code" className="text-sm font-semibold">
              {ar ? "رمز المهمة (اختياري)" : "Task Code (Optional)"}
            </Label>
            <Input
              id="task_code"
              placeholder={ar ? "مثال: 27-054-00" : "e.g., 27-054-00"}
              value={taskCode}
              onChange={(e) => setTaskCode(e.target.value)}
              className="max-w-md font-mono"
            />
            <p className="text-xs text-muted-foreground">
              {ar 
                ? "إذا تركت الحقل فارغاً، سيتم استخراج جميع الأكواد من كافة الملفات إلى ملف Excel." 
                : "If left blank, all codes from all files will be extracted to an Excel file."}
            </p>
          </div>
        </CardContent>
      </Card>

      <ModuleRunner
        moduleKey="task_extractor"
        title="Task Extractor"
        titleAr="استخراج المهام"
        description="Pick PDFs to extract maintenance task codes from (RegEx + OCR) via the Python worker."
        descriptionAr="اختر ملفات PDF لاستخراج رموز المهام منها (RegEx + OCR) عبر Python worker."
        icon={FileSearch}
        acceptedKinds={["pdf"]}
        minFiles={1}
        extraInput={{ task_code: taskCode }}
      />
      <TaskExtractorResults />
    </div>
  );
}

interface ExtractedTask {
  file: string;
  page: number;
  code: string;
}

function TaskExtractorResults() {
  const { lang } = useI18n();
  const ar = lang === "ar";
  const [search, setSearch] = useState("");
  const [sortField, setSortField] = useState<keyof ExtractedTask>("file");
  const [sortDesc, setSortDesc] = useState(false);

  // Poll for the latest done job for task_extractor
  const { data: latestJobs } = useQuery({
    queryKey: ["latest_done_job", "task_extractor"],
    queryFn: async () => {
      const jobs = await ApiClient.fetch("/jobs?module_key=task_extractor&status=done&limit=1");
      return jobs;
    },
    refetchInterval: 3000,
  });

  const latestJob = latestJobs && latestJobs.length > 0 ? latestJobs[0] : null;

  const outputRefs = latestJob?.output_refs as { files?: any[] } | null;
  const inputRefs = latestJob?.input_refs as { task_code?: string } | null;
  const isFullMode = !!inputRefs?.task_code;
  
  const filesList: { name: string; url: string }[] = (outputRefs?.files || []).map((f: any) =>
    typeof f === "string" ? { name: f.split("/").pop() || f, url: f } : f
  );

  const jsonFile = filesList.find((f) => f.name.endsWith(".json") && !f.name.endsWith("no_results.json"));
  const noResultsFile = filesList.find((f) => f.name.endsWith("no_results.json"));
  const pdfFiles = filesList.filter((f) => f.name.endsWith(".pdf"));
  const xlsxFile = filesList.find((f) => f.name.endsWith(".xlsx"));

  const { data: tasks, isLoading, error } = useQuery({
    queryKey: ["tasks_json", jsonFile?.url],
    enabled: !!jsonFile && !isFullMode,
    queryFn: async () => {
      const res = await fetch(jsonFile!.url);
      if (!res.ok) throw new Error("Failed to fetch JSON");
      return (await res.json()) as ExtractedTask[];
    },
  });

  const filteredTasks = useMemo(() => {
    if (!tasks) return [];
    let result = tasks;
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(
        (t) =>
          t.code.toLowerCase().includes(q) ||
          t.file.toLowerCase().includes(q) ||
          t.page.toString().includes(q)
      );
    }
    
    result = [...result].sort((a, b) => {
      let aVal = a[sortField];
      let bVal = b[sortField];
      
      if (typeof aVal === "string" && typeof bVal === "string") {
        return sortDesc ? bVal.localeCompare(aVal) : aVal.localeCompare(bVal);
      }
      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortDesc ? bVal - aVal : aVal - bVal;
      }
      return 0;
    });

    return result;
  }, [tasks, search, sortField, sortDesc]);

  const toggleSort = (field: keyof ExtractedTask) => {
    if (sortField === field) {
      setSortDesc(!sortDesc);
    } else {
      setSortField(field);
      setSortDesc(false);
    }
  };

  if (!latestJob) {
    return null; // Don't show anything if no jobs have ever completed
  }

  return (
    <Card className="border-t-4 border-t-primary shadow-sm">
      <CardHeader className="pb-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <CardTitle className="text-lg flex items-center gap-2">
              <Table2 className="size-5 text-primary" />
              {ar ? "أحدث النتائج المستخرجة" : "Latest Extraction Results"}
              {isFullMode && <Badge variant="secondary" className="font-mono">{inputRefs?.task_code}</Badge>}
            </CardTitle>
            <CardDescription className="mt-1">
              {ar
                ? `نتائج المهمة ${latestJob.id.slice(0, 8)} (${new Date(latestJob.created_at).toLocaleString()})`
                : `Results from job ${latestJob.id.slice(0, 8)} (${new Date(latestJob.created_at).toLocaleString()})`}
            </CardDescription>
          </div>
          
          {!isFullMode && (
            <div className="flex flex-col sm:flex-row gap-3 w-full sm:w-auto">
              <div className="relative w-full sm:w-72">
                <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
                <Input
                  placeholder={ar ? "ابحث في المهام، الملفات..." : "Search tasks, files..."}
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-9 h-9"
                />
              </div>
              
              {xlsxFile && (
                <Button 
                  variant="outline" 
                  size="sm" 
                  className="h-9 gap-2 shrink-0 border-green-600/30 text-green-700 hover:bg-green-50 hover:text-green-800 dark:text-green-400 dark:hover:bg-green-950/50"
                  onClick={() => {
                    window.open(xlsxFile.url, "_blank", "noopener,noreferrer");
                  }}
                >
                  <Download className="size-4" />
                  {ar ? "تصدير إلى Excel" : "Export to Excel"}
                </Button>
              )}
            </div>
          )}
        </div>
      </CardHeader>
      
      <CardContent className="p-0">
        {isFullMode ? (
          // Full Mode: Display PDF downloads
          <div className="p-6">
            {noResultsFile && pdfFiles.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <FileSearch className="size-10 mx-auto mb-3 opacity-20" />
                <p>{ar ? "لم يتم العثور على أية صفحات تطابق الكود المدخل." : "No pages found matching the provided task code."}</p>
              </div>
            ) : pdfFiles.length > 0 ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {pdfFiles.map((pdfFile, i) => (
                  <Button
                    key={i}
                    variant="outline"
                    className="h-auto p-4 justify-start text-left flex gap-3"
                    onClick={() => {
                      window.open(pdfFile.url, "_blank", "noopener,noreferrer");
                    }}
                  >
                    <div className="bg-primary/10 p-2 rounded shrink-0">
                      <FileText className="size-5 text-primary" />
                    </div>
                    <div className="truncate">
                      <div className="font-medium truncate">{pdfFile.name}</div>
                      <div className="text-xs text-muted-foreground">{ar ? "تحميل المستند" : "Download PDF"}</div>
                    </div>
                  </Button>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Loader2 className="size-6 animate-spin text-primary mx-auto mb-2" />
                <p>{ar ? "جاري معالجة الملفات..." : "Processing files..."}</p>
              </div>
            )}
          </div>
        ) : (
          // Legacy Mode: Display Table
          isLoading ? (
            <div className="p-12 flex flex-col items-center justify-center text-muted-foreground gap-3">
              <Loader2 className="size-6 animate-spin text-primary" />
              <p className="text-sm">{ar ? "جاري تحميل البيانات..." : "Loading data..."}</p>
            </div>
          ) : error ? (
            <div className="p-8 text-center text-destructive text-sm">
              {ar ? "حدث خطأ أثناء جلب النتائج" : "Failed to load results"}: {error.message}
            </div>
          ) : !tasks || tasks.length === 0 ? (
            <div className="p-12 text-center text-muted-foreground">
              <FileJson className="size-10 mx-auto mb-3 opacity-20" />
              <p className="text-sm">{ar ? "لم يتم العثور على أية مهام" : "No tasks extracted"}</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader className="bg-muted/30">
                  <TableRow>
                    <TableHead className="w-1/2 cursor-pointer" onClick={() => toggleSort("file")}>
                      <div className="flex items-center gap-2">
                        <FileText className="size-3.5" />
                        {ar ? "الملف المصدر" : "Source File"}
                        <ArrowUpDown className="size-3 opacity-50" />
                      </div>
                    </TableHead>
                    <TableHead className="w-[15%] cursor-pointer" onClick={() => toggleSort("page")}>
                      <div className="flex items-center gap-2">
                        <Hash className="size-3.5" />
                        {ar ? "الصفحة" : "Page"}
                        <ArrowUpDown className="size-3 opacity-50" />
                      </div>
                    </TableHead>
                    <TableHead className="w-[35%] cursor-pointer" onClick={() => toggleSort("code")}>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-[10px] uppercase font-normal py-0">Code</Badge>
                        {ar ? "رمز المهمة" : "Task Code"}
                        <ArrowUpDown className="size-3 opacity-50" />
                      </div>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredTasks.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3} className="h-24 text-center text-muted-foreground text-sm">
                        {ar ? "لا توجد نتائج تطابق بحثك." : "No results match your search."}
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredTasks.map((t, i) => (
                      <TableRow key={`${t.file}-${t.page}-${t.code}-${i}`} className="hover:bg-muted/20">
                        <TableCell className="font-medium text-sm max-w-[200px] truncate" title={t.file}>
                          {t.file}
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary" className="font-mono">{t.page}</Badge>
                        </TableCell>
                        <TableCell>
                          <Badge className="font-mono text-sm tracking-wide bg-primary/10 text-primary hover:bg-primary/20 border-primary/20">
                            {t.code}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
              <div className="p-3 bg-muted/20 border-t flex justify-between items-center text-xs text-muted-foreground">
                <div>
                  {ar ? `عرض ${filteredTasks.length} من أصل ${tasks.length} مهمة` : `Showing ${filteredTasks.length} of ${tasks.length} tasks`}
                </div>
              </div>
            </div>
          )
        )}
      </CardContent>
    </Card>
  );
}

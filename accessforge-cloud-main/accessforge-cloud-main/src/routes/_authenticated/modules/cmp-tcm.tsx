import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { FolderTree } from "lucide-react";
import { ModuleRunner } from "@/components/app/ModuleRunner";
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

export const Route = createFileRoute("/_authenticated/modules/cmp-tcm")({
  head: () => ({ meta: [{ title: "CMP / TCM · REDSEA" }] }),
  component: CmpTcmPage,
});

const CHECK_OPTIONS = [
  ...Array.from({ length: 11 }, (_, i) => `A${i + 1}`),
  ...Array.from({ length: 6 }, (_, i) => `C${i + 1}`),
  "120DY", "240DY", "12MO", "16MO", "2000FC"
];

function CmpTcmPage() {
  const { lang } = useI18n();
  const ar = lang === "ar";
  
  const [checkCode, setCheckCode] = useState("");

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
              {CHECK_OPTIONS.map((code) => (
                <SelectItem key={code} value={code}>
                  {code}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
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
      icon={FolderTree}
      acceptedKinds={["pdf", "excel"]}
      minFiles={1}
      extraControls={extraControls}
      extraInput={{ check: checkCode }}
    />
  );
}

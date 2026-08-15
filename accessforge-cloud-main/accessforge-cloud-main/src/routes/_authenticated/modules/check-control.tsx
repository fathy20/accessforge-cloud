import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
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
import { MODULE_ICONS } from "@/lib/modules/icons";

export const Route = createFileRoute("/_authenticated/modules/check-control")({
  head: () => ({ meta: [{ title: "Check Control · REDSEA" }] }),
  component: CheckControlPage,
});

const CHECK_OPTIONS = [
  ...Array.from({ length: 11 }, (_, i) => `A${i + 1}`),
  ...Array.from({ length: 6 }, (_, i) => `C${i + 1}`),
  "120DY", "240DY", "12MO", "16MO", "2000FC"
];

function CheckControlPage() {
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
              <SelectValue placeholder={ar ? "اختر الفحص..." : "Select check..."} />
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
      moduleKey="check_control"
      title="Check Control"
      titleAr="التحكم في الفحوصات"
      description="Import CSV check definitions and manage check execution data."
      descriptionAr="استيراد تعريفات الفحوصات من CSV وإدارة بيانات تنفيذها."
      icon={MODULE_ICONS.check_control}
      acceptedKinds={["csv", "excel"]}
      extraControls={extraControls}
      extraInput={{ check: checkCode }}
      supportsDatabase={true}
    />
  );
}

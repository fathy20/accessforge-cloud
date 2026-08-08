import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { ModuleRunner } from "@/components/app/ModuleRunner";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/lib/i18n";
import { MODULE_ICONS } from "@/lib/modules/icons";

export const Route = createFileRoute("/_authenticated/modules/task-stamping")({
  head: () => ({ meta: [{ title: "Task Stamping · REDSEA" }] }),
  component: TaskStampingPage,
});

function TaskStampingPage() {
  const { lang } = useI18n();
  const ar = lang === "ar";
  
  const [tail, setTail] = useState("");
  const [station, setStation] = useState("");
  const [date, setDate] = useState("");

  const extraControls = (
    <Card className="border-primary/20 bg-primary/5">
      <CardContent className="p-4 grid sm:grid-cols-3 gap-4">
        <div className="space-y-1.5">
          <Label>{ar ? "رقم الطائرة (Tail Number)" : "Tail Number"}</Label>
          <Input 
            value={tail} 
            onChange={(e) => setTail(e.target.value.toUpperCase())} 
            placeholder="e.g. A6-EGV" 
            className="bg-background"
          />
        </div>
        <div className="space-y-1.5">
          <Label>{ar ? "المحطة (Station)" : "Station"}</Label>
          <Input 
            value={station} 
            onChange={(e) => setStation(e.target.value.toUpperCase())} 
            placeholder="e.g. DXB" 
            className="bg-background"
          />
        </div>
        <div className="space-y-1.5">
          <Label>{ar ? "التاريخ (Date)" : "Date"}</Label>
          <Input 
            type="date" 
            value={date} 
            onChange={(e) => setDate(e.target.value)} 
            className="bg-background"
          />
        </div>
      </CardContent>
    </Card>
  );

  return (
    <ModuleRunner
      moduleKey="task_stamping"
      title="Task Stamping"
      titleAr="ختم المهام"
      description="Stamp Tail / Station / Date onto selected PDFs."
      descriptionAr="ختم رقم الطائرة والمحطة والتاريخ على ملفات PDF المختارة."
      icon={MODULE_ICONS.task_stamping}
      acceptedKinds={["pdf"]}
      extraControls={extraControls}
      extraInput={{ tail, station, date }}
    />
  );
}

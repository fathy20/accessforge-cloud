import { useI18n } from "@/lib/i18n";
import { Database, UploadCloud } from "lucide-react";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Card } from "@/components/ui/card";

export type DataSource = "files" | "db";

interface DataSourceToggleProps {
  value: DataSource;
  onChange: (v: DataSource) => void;
  className?: string;
}

export function DataSourceToggle({ value, onChange, className = "" }: DataSourceToggleProps) {
  const { lang } = useI18n();
  const ar = lang === "ar";

  return (
    <Card className={`p-4 ${className}`}>
      <div className="mb-3 text-sm font-medium">
        {ar ? "مصدر البيانات (Data Source)" : "Data Source"}
      </div>
      <RadioGroup
        value={value}
        onValueChange={(val) => onChange(val as DataSource)}
        className="grid grid-cols-2 gap-4"
      >
        <Label
          htmlFor="src-files"
          className={`flex flex-col items-center justify-center rounded-md border-2 border-muted bg-popover p-4 hover:bg-accent hover:text-accent-foreground cursor-pointer [&:has([data-state=checked])]:border-primary ${
            value === "files" ? "border-primary bg-primary/5" : ""
          }`}
        >
          <RadioGroupItem value="files" id="src-files" className="sr-only" />
          <UploadCloud className="mb-2 size-6" />
          <span className="text-sm font-medium">
            {ar ? "رفع ملفات" : "Upload Files"}
          </span>
        </Label>
        
        <Label
          htmlFor="src-db"
          className={`flex flex-col items-center justify-center rounded-md border-2 border-muted bg-popover p-4 hover:bg-accent hover:text-accent-foreground cursor-pointer [&:has([data-state=checked])]:border-primary ${
            value === "db" ? "border-primary bg-primary/5" : ""
          }`}
        >
          <RadioGroupItem value="db" id="src-db" className="sr-only" />
          <Database className="mb-2 size-6" />
          <span className="text-sm font-medium">
            {ar ? "قاعدة البيانات" : "Database"}
          </span>
        </Label>
      </RadioGroup>
    </Card>
  );
}

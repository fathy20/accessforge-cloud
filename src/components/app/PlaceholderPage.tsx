import { Card, CardContent } from "@/components/ui/card";
import { Construction } from "lucide-react";

export function PlaceholderPage({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <Card>
        <CardContent className="p-10 grid place-items-center text-center text-muted-foreground">
          <Construction className="size-10 mb-3 text-primary" />
          <p className="text-sm">This module's UI is scaffolded — implementation coming in the next phase.</p>
        </CardContent>
      </Card>
    </div>
  );
}

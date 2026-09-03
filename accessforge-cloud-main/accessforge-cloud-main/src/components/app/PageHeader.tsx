import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  icon?: LucideIcon;
  /** Right-aligned controls (filters, primary actions). Wraps under the title on narrow screens. */
  actions?: ReactNode;
  className?: string;
}

/**
 * The one page-title block every authenticated page uses, so the type ramp
 * (heading-1 over body/muted) and the title/actions layout stay identical
 * across routes instead of being re-typed per page.
 */
export function PageHeader({
  title,
  description,
  icon: Icon,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <div className={cn("flex flex-wrap items-start justify-between gap-4", className)}>
      <div className="min-w-0">
        <h1 className="flex items-center gap-2 text-heading-1 tracking-tight text-fg-primary">
          {Icon && <Icon className="size-5 shrink-0 text-primary" aria-hidden="true" />}
          {title}
        </h1>
        {description && <p className="mt-1 max-w-2xl text-body text-fg-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

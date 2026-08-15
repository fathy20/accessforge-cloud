import {
  CircleHelp,
  FileSearch,
  FolderTree,
  GaugeCircle,
  Layers,
  ListChecks,
  Mailbox,
  Settings,
  ShieldCheck,
  Stamp,
  Table2,
  Users2,
  type LucideIcon,
} from "lucide-react";

export const MODULE_ICONS: Record<string, LucideIcon> = {
  task_extractor: FileSearch,
  task_stamping: Stamp,
  effectivity: Table2,
  check_control: ListChecks,
  utilization: GaugeCircle,
  cmp_tcm: FolderTree,
  cover_merge: Layers,
  mail_merge: Mailbox,
  crew_hours: Users2,
  tcm_indexing: FolderTree,
  admin_users: Users2,
  admin_audit: ShieldCheck,
  admin_settings: Settings,
};

export const DEFAULT_MODULE_ICON = CircleHelp;

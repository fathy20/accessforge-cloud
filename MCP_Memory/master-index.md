# MCP Memory Master Index
**AccessForge / FlightAssist Web Knowledge Base**

Welcome to the central nervous system of the AccessForge Project. This Knowledge Base serves as the primary Long-Term Memory for all Development Agents and Human Engineers.

## 🧭 Starting Points for Agents
Based on your current task, start here:
- **Want to understand the big picture?** Read [system/overview.md](system/overview.md) and [mapping/app2-vs-web.md](mapping/app2-vs-web.md)
- **Want to implement/edit a specific Module?** Look in `modules/` (e.g., [modules/task-extractor.md](modules/task-extractor.md)) then deep-dive into its [business-logic/](business-logic/).
- **Need to write SQL or map an Entity?** Check [database/erd.md](database/erd.md) and [entities/](entities/).
- **Curious why a technical choice was made?** Read the [decisions/](decisions/) folder (ADRs).
- **Need to write Tests?** Go to [testing/](testing/) to ensure feature parity with App2.

---

## 📁 Knowledge Base Directory

### 1. `system/`
High-level context, technical stack, and system architecture.

### 2. `inventory/`
Complete index of the legacy App2 (Forms, Classes, Dependencies, Services) before reverse engineering.

### 3. `reverse-engineering/`
Deep-dive into App2 internals (Data flow, Event flow, Sequence diagrams) to understand *how* it worked.

### 4. `business-logic/`
The raw, UI-agnostic rules extracted from App2 (e.g., how Effectivity mapping actually works).

### 5. `modules/`
Detailed specs for the new Web Modules (Task Extractor, Check Control). Connects the UI to the Business Logic.

### 6. `entities/`
Database abstractions (Project, Task, Aircraft, User) describing fields and relations.

### 7. `database/`
ERDs, Table mappings, and SQL details (derived strictly after Business Logic extraction).

### 8. `api/`
Endpoint definitions, RPC calls, and Supabase RLS policies.

### 9. `frontend/`
Specific UI screen logic (Dashboard, Login) and TanStack routing definitions.

### 10. `workers/`
Background Node.js/Python workers handling async jobs (OCR, PDF).

### 11. `testing/`
Test scenarios, regression tests, and migration validation.

### 12. `mapping/`
Direct comparison between App2 Desktop and AccessForge Web, tracking missing features.

### 13. `decisions/`
Architecture Decision Records (ADRs) to prevent circular technical debates.

### 14. `standards/`
Coding standards (React, TypeScript, Supabase, Naming Conventions).

### 15. `development/`
Living documents: `roadmap.md`, `decision-log.md`, `technical-debt.md`. **Update these when you finish a task!**

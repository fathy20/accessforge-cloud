# Check Control Module
## Purpose
Manage and ingest maintenance checks via CSV.
## Owner
Web Development Team
## Dependencies
- Supabase (Auth & DB)
- Background Worker: None (Direct DB)
## Database Tables
- projects, jobs, job_logs, aircraft_checks
## API
- Supabase Client (RPC & CRUD)
## Permissions
- Requires can_run in module_access for this specific module key.
## Background Worker
N/A - Direct synchronous DB insertion.
## Workflow
1. User interacts with UI.
2. Entry created in DB.
3. Background job triggered.
4. Results polled and displayed.
## Known Issues
- Pending initial implementation.
## Future Improvements
- Add batch processing support.

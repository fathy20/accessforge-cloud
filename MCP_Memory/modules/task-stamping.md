# Task Stamping Module
## Purpose
Stamp tail, station, and date on PDFs.
## Owner
Web Development Team
## Dependencies
- Supabase (Auth & DB)
- Background Worker: pdf-worker
## Database Tables
- projects, jobs, job_logs, uploads
## API
- Supabase Client (RPC & CRUD)
## Permissions
- Requires can_run in module_access for this specific module key.
## Background Worker
Downloads PDF, applies text layer, uploads stamped version.
## Workflow
1. User interacts with UI.
2. Entry created in DB.
3. Background job triggered.
4. Results polled and displayed.
## Known Issues
- Pending initial implementation.
## Future Improvements
- Add batch processing support.

# Task Extractor Module
## Purpose
Extract tasks from PDFs via OCR and Regex.
## Owner
Web Development Team
## Dependencies
- Supabase (Auth & DB)
- Background Worker: ocr-worker
## Database Tables
- projects, jobs, job_logs, tasks
## API
- Supabase Client (RPC & CRUD)
## Permissions
- Requires can_run in module_access for this specific module key.
## Background Worker
Reads PDFs from Storage, runs Tesseract OCR, parses text, inserts tasks.
## Workflow
1. User interacts with UI.
2. Entry created in DB.
3. Background job triggered.
4. Results polled and displayed.
## Known Issues
- Pending initial implementation.
## Future Improvements
- Add batch processing support.

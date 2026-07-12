# Task Extraction Logic
**Goal**: Identify and extract maintenance task details from unstructured PDF documents.
**Rules**:
1. Uses Regex and OCR to scan document content.
2. Identifies variables like Task Code, Title, Chapter, and Effectivity.
3. Once extracted, creates a record in the 	asks table mapped to the source_upload_id and project_id.
**App2 Behavior**: This used to freeze the desktop app while iterating over PDF pages. In the Web, it must run entirely in a background worker, updating the jobs progress column.

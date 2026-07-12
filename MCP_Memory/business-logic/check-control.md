# Check Control Logic
**Goal**: Manage and ingest maintenance checks via CSV.
**Rules**:
1. CSV columns are mapped to internal data structures.
2. Performs validation on the imported records to ensure data integrity (no missing required fields).
3. Connects the checks to the specific Aircraft (Tail Number) through the Project context.

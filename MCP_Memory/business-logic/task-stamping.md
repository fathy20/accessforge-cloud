# Task Stamping Logic
**Goal**: Apply visual stamps (Tail number, station, date) to PDF documents.
**Rules**:
1. Stamp coordinates must be calculated based on page size.
2. Must run purely asynchronously (Worker), replacing original files or creating new versions in the uploads table.

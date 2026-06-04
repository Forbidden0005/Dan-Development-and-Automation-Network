Phase 1 — Context
Bump OLLAMA_NUM_CTX to 32768 in the bat file
Build a Project Loader tool: scans a project directory, builds a condensed map of files/functions/classes, injects it into Dan's context at session start

Phase 2 — Code Execution Loop
Dan has Bash but no structured execution loop. What's needed:

RunCode tool — runs a snippet in the right language, captures stdout/stderr, returns structured result
IterateFix pattern — run → read error → fix → rerun, up to N times automatically
TestLoop — run test suite, read failures, fix, rerun until green

Phase 3 — Codebase Intelligence
This is what makes the biggest difference for real projects:

Project Indexer — walks the codebase, extracts symbols (functions, classes, imports), stores in SQLite
SemanticSearch tool — uses embeddings (via sentence-transformers or ollama embed) to find relevant code by meaning, not filename
DependencyGraph — knows what imports what, so changing one file shows what else might break
SymbolLookup — "where is process_payment defined?" answers instantly
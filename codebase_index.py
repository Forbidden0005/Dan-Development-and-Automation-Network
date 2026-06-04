"""
codebase_index.py -- Phase 3 Codebase Intelligence for Dan.

Walks a project, extracts every symbol (functions, classes, methods) with
signatures and docstrings, stores in SQLite with FTS5 full-text search and
optional Ollama vector embeddings for semantic search.

Tools registered:
  IndexProject    -- scan & index a project into SQLite (incremental)
  SymbolLookup    -- find where any function/class is defined (file:line)
  FindUsages      -- find every file that references a symbol
  DependencyGraph -- show what a file imports and what imports it
  SemanticSearch  -- find relevant code by meaning (uses Ollama embeddings
                     or falls back to FTS keyword search)
"""

import ast
import hashlib
import json
import math
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import tool_registry as registry
from config import USER_DATA_DIR

# ── Constants ─────────────────────────────────────────────────────────────────

INDEX_DIR = USER_DATA_DIR / "index"
INDEX_DIR.mkdir(parents=True, exist_ok=True)

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    "dist", "build", ".next", ".nuxt", "target", ".cargo",
    ".mypy_cache", ".pytest_cache", ".tox", "coverage",
    "obj", "bin", ".vs", ".idea", "site-packages",
}

CODE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs",
    ".go", ".rs", ".rb", ".php", ".java", ".kt", ".cs",
    ".cpp", ".cc", ".c", ".h", ".hpp", ".swift",
}

MAX_FILE_SIZE = 500_000    # 500 KB
EMBED_MODEL   = "nomic-embed-text"   # Ollama model for embeddings


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class Symbol:
    name:         str
    kind:         str     # 'function', 'class', 'method', 'constant'
    line:         int
    signature:    str
    docstring:    str
    parent_class: str = ""


@dataclass
class FileDep:
    module_name: str
    is_local:    bool
    from_clause: str = ""


# ── DB helpers ────────────────────────────────────────────────────────────────

def _db_path(project_root: str) -> Path:
    h = hashlib.md5(project_root.encode()).hexdigest()[:12]
    name = Path(project_root).name
    return INDEX_DIR / f"{name}_{h}.db"


def _open_db(project_root: str) -> sqlite3.Connection:
    db = sqlite3.connect(str(_db_path(project_root)))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    _init_schema(db)
    return db


def _init_schema(db: sqlite3.Connection) -> None:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS files (
            id          INTEGER PRIMARY KEY,
            path        TEXT UNIQUE,
            rel_path    TEXT,
            language    TEXT,
            line_count  INTEGER,
            file_hash   TEXT,
            indexed_at  REAL
        );

        CREATE TABLE IF NOT EXISTS symbols (
            id           INTEGER PRIMARY KEY,
            file_id      INTEGER REFERENCES files(id) ON DELETE CASCADE,
            name         TEXT,
            kind         TEXT,
            line         INTEGER,
            signature    TEXT,
            docstring    TEXT,
            parent_class TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
        CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id);

        CREATE TABLE IF NOT EXISTS deps (
            id          INTEGER PRIMARY KEY,
            file_id     INTEGER REFERENCES files(id) ON DELETE CASCADE,
            module_name TEXT,
            is_local    INTEGER,
            from_clause TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_deps_file   ON deps(file_id);
        CREATE INDEX IF NOT EXISTS idx_deps_module ON deps(module_name);

        CREATE TABLE IF NOT EXISTS embeddings (
            symbol_id    INTEGER PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
            embed_text   TEXT,
            vector_json  TEXT
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
            name, signature, docstring,
            content=symbols, content_rowid=id,
            tokenize='unicode61'
        );
    """)
    db.commit()


# ── Symbol extraction ─────────────────────────────────────────────────────────

def _py_args(args: ast.arguments) -> str:
    parts = []
    defaults_offset = len(args.args) - len(args.defaults)
    for i, arg in enumerate(args.args):
        a = arg.arg
        if arg.annotation and isinstance(arg.annotation, ast.Name):
            a += f": {arg.annotation.id}"
        elif arg.annotation and isinstance(arg.annotation, ast.Constant):
            a += f": {arg.annotation.value}"
        di = i - defaults_offset
        if di >= 0:
            d = args.defaults[di]
            if isinstance(d, ast.Constant):
                a += f" = {d.value!r}"
        parts.append(a)
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")
    return ", ".join(parts)


def _extract_python(content: str) -> tuple[list[Symbol], list[FileDep]]:
    symbols: list[Symbol] = []
    deps:    list[FileDep] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return symbols, deps

    for node in tree.body:
        # Top-level functions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            sig    = f"{prefix} {node.name}({_py_args(node.args)})"
            doc    = (ast.get_docstring(node) or "").split("\n")[0][:120]
            symbols.append(Symbol(node.name, "function", node.lineno, sig, doc))

        # Classes + their methods
        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(
                b.id for b in node.bases if isinstance(b, ast.Name)
            )
            sig = f"class {node.name}" + (f"({bases})" if bases else "")
            doc = (ast.get_docstring(node) or "").split("\n")[0][:120]
            symbols.append(Symbol(node.name, "class", node.lineno, sig, doc))

            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    prefix = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                    msig   = f"{prefix} {item.name}({_py_args(item.args)})"
                    mdoc   = (ast.get_docstring(item) or "").split("\n")[0][:120]
                    symbols.append(Symbol(
                        item.name, "method", item.lineno,
                        msig, mdoc, parent_class=node.name
                    ))

        # Imports
        elif isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split(".")[0]
                deps.append(FileDep(module, is_local=False))

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            is_local = node.level > 0  # relative import = local
            base = module.split(".")[0] if module else ""
            names = ", ".join(a.name for a in node.names[:4])
            deps.append(FileDep(base or ".", is_local, from_clause=names))

    return symbols, deps


def _extract_js_ts(content: str) -> tuple[list[Symbol], list[FileDep]]:
    symbols: list[Symbol] = []
    deps:    list[FileDep] = []

    # Classes
    for m in re.finditer(r"(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?", content):
        name, base = m.group(1), m.group(2) or ""
        line = content[:m.start()].count("\n") + 1
        sig  = f"class {name}" + (f" extends {base}" if base else "")
        symbols.append(Symbol(name, "class", line, sig, ""))

    # Functions (named)
    for m in re.finditer(
        r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]{0,80})\)",
        content
    ):
        name, args = m.group(1), m.group(2).strip()
        line = content[:m.start()].count("\n") + 1
        symbols.append(Symbol(name, "function", line, f"function {name}({args})", ""))

    # Arrow functions assigned to const/let/var
    for m in re.finditer(
        r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]{0,80})\)\s*=>",
        content
    ):
        name, args = m.group(1), m.group(2).strip()
        line = content[:m.start()].count("\n") + 1
        symbols.append(Symbol(name, "function", line, f"const {name} = ({args}) =>", ""))

    # Imports
    for m in re.finditer(r"(?:import|require)\s*\(?['\"]([^'\"]+)['\"]", content):
        mod  = m.group(1)
        local = mod.startswith(".")
        base = mod.lstrip("./").split("/")[0] if not local else mod
        deps.append(FileDep(base, is_local=local))

    return symbols, deps


def _extract_go(content: str) -> tuple[list[Symbol], list[FileDep]]:
    symbols: list[Symbol] = []
    deps:    list[FileDep] = []

    for m in re.finditer(r"type\s+(\w+)\s+struct", content):
        line = content[:m.start()].count("\n") + 1
        symbols.append(Symbol(m.group(1), "class", line, f"type {m.group(1)} struct", ""))

    for m in re.finditer(
        r"^func\s+(?:\(\w+\s+\*?(\w+)\)\s+)?(\w+)\(([^)]{0,80})\)",
        content, re.MULTILINE
    ):
        recv, name, args = m.group(1) or "", m.group(2), m.group(3).strip()
        line = content[:m.start()].count("\n") + 1
        kind = "method" if recv else "function"
        sig  = f"func ({recv}) {name}({args})" if recv else f"func {name}({args})"
        symbols.append(Symbol(name, kind, line, sig, "", parent_class=recv))

    for m in re.finditer(r'"([\w./]+)"', content):
        mod = m.group(1)
        local = "/" in mod and not mod.startswith("github.com")
        deps.append(FileDep(mod.split("/")[-1], is_local=local))

    return symbols, deps


def _extract_rust(content: str) -> tuple[list[Symbol], list[FileDep]]:
    symbols: list[Symbol] = []
    deps:    list[FileDep] = []

    for m in re.finditer(r"(?:pub\s+)?struct\s+(\w+)|(?:pub\s+)?enum\s+(\w+)", content):
        name = m.group(1) or m.group(2)
        line = content[:m.start()].count("\n") + 1
        symbols.append(Symbol(name, "class", line, f"struct/enum {name}", ""))

    for m in re.finditer(
        r"(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\(([^)]{0,80})\)(?:\s*->\s*([^\{]{0,40}))?",
        content
    ):
        name, args, ret = m.group(1), m.group(2).strip(), (m.group(3) or "").strip()
        line = content[:m.start()].count("\n") + 1
        sig  = f"fn {name}({args})" + (f" -> {ret}" if ret else "")
        symbols.append(Symbol(name, "function", line, sig, ""))

    for m in re.finditer(r"use\s+([\w:]+)", content):
        parts = m.group(1).split("::")
        deps.append(FileDep(parts[0], is_local=False))

    return symbols, deps


def _extract_symbols(content: str, ext: str
                     ) -> tuple[list[Symbol], list[FileDep]]:
    if ext in (".py", ".pyw"):
        return _extract_python(content)
    elif ext in (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".mts"):
        return _extract_js_ts(content)
    elif ext == ".go":
        return _extract_go(content)
    elif ext == ".rs":
        return _extract_rust(content)
    return [], []


def _file_hash(path: Path) -> str:
    h = hashlib.md5()
    h.update(path.read_bytes()[:65536])   # hash first 64 KB
    return h.hexdigest()


# ── Indexer ───────────────────────────────────────────────────────────────────

def _index_project(root_str: str, force: bool = False) -> str:
    root = Path(root_str).resolve()
    if not root.is_dir():
        return f"Error: not a directory: {root_str}"

    db = _open_db(str(root))
    t0 = time.time()
    indexed = updated = skipped = errors = 0

    for fp in sorted(root.rglob("*")):
        if fp.is_dir():
            continue
        if any(part in SKIP_DIRS for part in fp.parts):
            continue
        if fp.suffix.lower() not in CODE_EXTS:
            continue
        try:
            if fp.stat().st_size > MAX_FILE_SIZE:
                continue
        except Exception:
            continue

        ext      = fp.suffix.lower()
        rel      = str(fp.relative_to(root))
        fhash    = _file_hash(fp)
        lang_map = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".jsx": "React", ".tsx": "React/TS", ".mjs": "JavaScript",
            ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
            ".java": "Java", ".kt": "Kotlin", ".cs": "C#",
            ".cpp": "C++", ".cc": "C++", ".c": "C",
            ".h": "C/C++", ".hpp": "C++", ".swift": "Swift",
        }
        lang = lang_map.get(ext, ext.lstrip(".").upper())

        # Check if file changed
        row = db.execute(
            "SELECT id, file_hash FROM files WHERE path=?", (str(fp),)
        ).fetchone()

        if row and row["file_hash"] == fhash and not force:
            skipped += 1
            continue

        try:
            content    = fp.read_text(encoding="utf-8", errors="replace")
            line_count = content.count("\n") + 1
            symbols, deps = _extract_symbols(content, ext)
        except Exception as e:
            errors += 1
            continue

        with db:
            if row:
                file_id = row["id"]
                db.execute("UPDATE files SET file_hash=?, line_count=?, indexed_at=? WHERE id=?",
                           (fhash, line_count, time.time(), file_id))
                db.execute("DELETE FROM symbols WHERE file_id=?", (file_id,))
                db.execute("DELETE FROM deps    WHERE file_id=?", (file_id,))
                updated += 1
            else:
                cur = db.execute(
                    "INSERT INTO files (path, rel_path, language, line_count, file_hash, indexed_at)"
                    " VALUES (?,?,?,?,?,?)",
                    (str(fp), rel, lang, line_count, fhash, time.time())
                )
                file_id = cur.lastrowid
                indexed += 1

            # Insert symbols
            sym_ids = []
            for s in symbols:
                cur = db.execute(
                    "INSERT INTO symbols (file_id, name, kind, line, signature, docstring, parent_class)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (file_id, s.name, s.kind, s.line, s.signature, s.docstring, s.parent_class)
                )
                sym_ids.append((cur.lastrowid, s.signature + " " + s.docstring))

            # Insert deps
            for d in deps:
                db.execute(
                    "INSERT INTO deps (file_id, module_name, is_local, from_clause)"
                    " VALUES (?,?,?,?)",
                    (file_id, d.module_name, 1 if d.is_local else 0, d.from_clause)
                )

            # Rebuild FTS for affected rows
            db.execute("DELETE FROM symbols_fts WHERE rowid IN "
                       "(SELECT id FROM symbols WHERE file_id=?)", (file_id,))
            for sym in db.execute(
                "SELECT id, name, signature, docstring FROM symbols WHERE file_id=?",
                (file_id,)
            ):
                db.execute(
                    "INSERT INTO symbols_fts(rowid, name, signature, docstring)"
                    " VALUES (?,?,?,?)",
                    (sym["id"], sym["name"], sym["signature"], sym["docstring"])
                )

    elapsed = time.time() - t0
    total   = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    sym_cnt = db.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
    db.close()

    lines = [
        f"Project index for: {root.name}",
        f"  Indexed: {indexed} new  |  Updated: {updated}  |  Skipped: {skipped} unchanged",
        f"  Errors:  {errors}",
        f"  Total:   {total} files  |  {sym_cnt} symbols",
        f"  Time:    {elapsed:.1f}s",
        f"  DB:      {_db_path(str(root)).name}",
    ]
    if errors:
        lines.append(f"  (some files could not be parsed)")
    return "\n".join(lines)


# ── Tool handlers ─────────────────────────────────────────────────────────────

def _require_db(project_root: str) -> tuple[Optional[sqlite3.Connection], str]:
    root = Path(project_root).resolve()
    db_path = _db_path(str(root))
    if not db_path.exists():
        return None, (
            f"No index found for: {root.name}\n"
            "Run IndexProject first: /project . then ask Dan to IndexProject"
        )
    return _open_db(str(root)), ""


def symbol_lookup(name: str, project_root: str = ".") -> str:
    """Find where a symbol (function/class/method) is defined."""
    db, err = _require_db(project_root)
    if not db: return err

    rows = db.execute("""
        SELECT s.name, s.kind, s.line, s.signature, s.docstring,
               s.parent_class, f.rel_path
        FROM symbols s JOIN files f ON s.file_id = f.id
        WHERE s.name = ? OR s.name LIKE ?
        ORDER BY s.kind, f.rel_path
        LIMIT 20
    """, (name, f"%{name}%")).fetchall()
    db.close()

    if not rows:
        return f"Symbol '{name}' not found in index. Run IndexProject to refresh."

    lines = [f"Symbol lookup: '{name}'  ({len(rows)} match(es))\n"]
    for r in rows:
        parent = f"  (in class {r['parent_class']})" if r["parent_class"] else ""
        lines.append(f"  [{r['kind']}] {r['rel_path']}:{r['line']}{parent}")
        lines.append(f"      {r['signature']}")
        if r["docstring"]:
            lines.append(f"      # {r['docstring'][:100]}")
        lines.append("")

    return "\n".join(lines)


def find_usages(name: str, project_root: str = ".") -> str:
    """Find every file that references a symbol by name (grep + dep graph)."""
    db, err = _require_db(project_root)
    if not db: return err
    root = Path(project_root).resolve()

    # Files that directly mention the name
    matches: list[tuple[str, int, str]] = []
    for fp in sorted(root.rglob("*")):
        if fp.is_dir() or any(p in SKIP_DIRS for p in fp.parts):
            continue
        if fp.suffix.lower() not in CODE_EXTS:
            continue
        try:
            lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
            for i, line in enumerate(lines, 1):
                if re.search(rf"\b{re.escape(name)}\b", line):
                    rel = str(fp.relative_to(root))
                    matches.append((rel, i, line.strip()[:100]))
                    if len(matches) >= 50:
                        break
        except Exception:
            continue
        if len(matches) >= 50:
            break

    db.close()
    if not matches:
        return f"No usages of '{name}' found in project."

    lines = [f"Usages of '{name}'  ({len(matches)} found):\n"]
    for rel, lineno, snippet in matches:
        lines.append(f"  {rel}:{lineno}")
        lines.append(f"      {snippet}")
    if len(matches) == 50:
        lines.append("\n  (showing first 50 matches)")
    return "\n".join(lines)


def dependency_graph(file_path: str, project_root: str = ".") -> str:
    """Show what a file imports AND what other files import it."""
    db, err = _require_db(project_root)
    if not db: return err
    root = Path(project_root).resolve()

    # Resolve the file
    fp     = Path(file_path)
    abs_fp = (root / fp) if not fp.is_absolute() else fp
    rel    = str(abs_fp.relative_to(root)) if abs_fp.is_relative_to(root) else file_path

    row = db.execute(
        "SELECT id, language FROM files WHERE rel_path=? OR path=?",
        (rel, str(abs_fp))
    ).fetchone()

    if not row:
        db.close()
        return (f"'{rel}' is not in the index. Run IndexProject first, "
                "or check the path is correct.")

    file_id = row["id"]

    # What this file imports
    imports = db.execute(
        "SELECT module_name, is_local, from_clause FROM deps WHERE file_id=?",
        (file_id,)
    ).fetchall()

    # What files import this file (reverse lookup by module/rel_path stem)
    stem        = Path(rel).stem
    imported_by = db.execute("""
        SELECT DISTINCT f.rel_path
        FROM deps d JOIN files f ON d.file_id = f.id
        WHERE d.module_name = ?
           OR d.module_name LIKE ?
        ORDER BY f.rel_path
        LIMIT 30
    """, (stem, f"%.{stem}")).fetchall()

    # Symbols defined in this file
    symbols = db.execute(
        "SELECT name, kind, line FROM symbols WHERE file_id=? ORDER BY line",
        (file_id,)
    ).fetchall()

    db.close()

    out = [f"Dependency graph: {rel}\n", "IMPORTS:"]
    local_imports  = [r for r in imports if r["is_local"]]
    extern_imports = [r for r in imports if not r["is_local"]]

    if local_imports:
        out.append("  Internal:")
        for r in local_imports:
            fc = f" (from {r['from_clause']})" if r["from_clause"] else ""
            out.append(f"    . {r['module_name']}{fc}")
    if extern_imports:
        out.append("  External:")
        for r in extern_imports[:20]:
            fc = f" (from {r['from_clause']})" if r["from_clause"] else ""
            out.append(f"    + {r['module_name']}{fc}")

    if not imports:
        out.append("  (none found)")

    out.append("\nIMPORTED BY:")
    if imported_by:
        for r in imported_by:
            out.append(f"  <- {r['rel_path']}")
    else:
        out.append("  (no other files import this module)")

    out.append(f"\nSYMBOLS DEFINED HERE ({len(symbols)}):")
    for s in symbols:
        parent = f"  [{s['kind']}]" if s["kind"] != "function" else ""
        out.append(f"  line {s['line']:4d}  {s['name']}{parent}")

    return "\n".join(out)


def semantic_search(query: str, project_root: str = ".",
                    top_k: int = 10, use_embeddings: bool = True) -> str:
    """
    Find code relevant to a natural-language query.

    If an Ollama embedding model is available (nomic-embed-text or similar),
    uses cosine similarity over stored vectors.
    Falls back to SQLite FTS5 keyword search automatically.
    """
    db, err = _require_db(project_root)
    if not db: return err

    results = []

    # Try vector search first
    if use_embeddings:
        results = _vector_search(db, query, top_k)

    # Fall back to FTS keyword search
    if not results:
        results = _fts_search(db, query, top_k)

    db.close()

    if not results:
        return (f"No results for: '{query}'\n"
                "Try IndexProject to refresh the index.")

    lines = [f"Semantic search: '{query}'  ({len(results)} result(s))\n"]
    for i, (score, name, kind, line, sig, doc, rel_path, parent) in enumerate(results, 1):
        parent_str = f"  [in {parent}]" if parent else ""
        score_str  = f"  score={score:.3f}" if score < 1.0 else ""
        lines.append(f"  {i}. {rel_path}:{line}  [{kind}] {name}{parent_str}{score_str}")
        lines.append(f"     {sig}")
        if doc:
            lines.append(f"     # {doc[:100]}")
        lines.append("")

    return "\n".join(lines)


def _fts_search(db: sqlite3.Connection, query: str,
                top_k: int) -> list[tuple]:
    """SQLite FTS5 keyword search."""
    # Sanitize query for FTS5
    safe = re.sub(r'[^\w\s]', ' ', query).strip()
    if not safe:
        return []
    try:
        rows = db.execute("""
            SELECT 1.0 as score,
                   s.name, s.kind, s.line, s.signature, s.docstring,
                   f.rel_path, s.parent_class
            FROM symbols_fts fts
            JOIN symbols s ON fts.rowid = s.id
            JOIN files   f ON s.file_id = f.id
            WHERE symbols_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (safe, top_k)).fetchall()
        return [tuple(r) for r in rows]
    except Exception:
        # FTS might not be populated -- fall back to LIKE search
        rows = db.execute("""
            SELECT 1.0, s.name, s.kind, s.line, s.signature, s.docstring,
                   f.rel_path, s.parent_class
            FROM symbols s JOIN files f ON s.file_id = f.id
            WHERE s.name LIKE ? OR s.signature LIKE ?
            LIMIT ?
        """, (f"%{query}%", f"%{query}%", top_k)).fetchall()
        return [tuple(r) for r in rows]


def _vector_search(db: sqlite3.Connection, query: str,
                   top_k: int) -> list[tuple]:
    """Cosine similarity search over stored Ollama embeddings."""
    # Check if any embeddings exist
    count = db.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    if count == 0:
        return []   # no embeddings yet → fall back to FTS

    # Embed the query
    q_vec = _get_embedding(query)
    if not q_vec:
        return []

    # Load all embeddings and score them
    rows   = db.execute("SELECT symbol_id, vector_json FROM embeddings").fetchall()
    scored = []
    for r in rows:
        try:
            vec  = json.loads(r["vector_json"])
            sim  = _cosine(q_vec, vec)
            scored.append((sim, r["symbol_id"]))
        except Exception:
            continue

    scored.sort(key=lambda x: -x[0])
    top_ids = [sid for _, sid in scored[:top_k]]

    if not top_ids:
        return []

    placeholders = ",".join("?" * len(top_ids))
    rows2 = db.execute(f"""
        SELECT s.name, s.kind, s.line, s.signature, s.docstring,
               f.rel_path, s.parent_class, s.id
        FROM symbols s JOIN files f ON s.file_id = f.id
        WHERE s.id IN ({placeholders})
    """, top_ids).fetchall()

    id_to_row = {r["id"]: r for r in rows2}
    results   = []
    for sim, sid in scored[:top_k]:
        if sid in id_to_row:
            r = id_to_row[sid]
            results.append((sim, r["name"], r["kind"], r["line"],
                            r["signature"], r["docstring"],
                            r["rel_path"], r["parent_class"]))
    return results


def _get_embedding(text: str) -> list[float]:
    """Get an embedding vector from Ollama."""
    try:
        import httpx
        r = httpx.post(
            "http://localhost:11434/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text[:512]},
            timeout=20,
        )
        if r.status_code == 200:
            return r.json().get("embedding", [])
    except Exception:
        pass
    return []


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag = math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(y*y for y in b))
    return dot / (mag + 1e-9)


def embed_project(project_root: str = ".") -> str:
    """
    Generate and store Ollama embeddings for all indexed symbols.
    Requires: ollama pull nomic-embed-text
    Enables true semantic search.
    """
    db, err = _require_db(project_root)
    if not db: return err

    symbols = db.execute(
        "SELECT id, name, signature, docstring FROM symbols "
        "WHERE id NOT IN (SELECT symbol_id FROM embeddings)"
    ).fetchall()

    if not symbols:
        db.close()
        return "All symbols already have embeddings."

    done = failed = 0
    for s in symbols:
        text = f"{s['name']} {s['signature']} {s['docstring']}".strip()[:512]
        vec  = _get_embedding(text)
        if vec:
            try:
                with db:
                    db.execute(
                        "INSERT OR REPLACE INTO embeddings (symbol_id, embed_text, vector_json)"
                        " VALUES (?,?,?)",
                        (s["id"], text, json.dumps(vec))
                    )
                done += 1
            except Exception:
                failed += 1
        else:
            failed += 1

    db.close()
    lines = [f"Embedding complete: {done} symbols embedded, {done+failed} attempted"]
    if failed:
        lines.append(
            f"  {failed} failed -- is '{EMBED_MODEL}' pulled?\n"
            f"  Run: ollama pull {EMBED_MODEL}"
        )
    lines.append("SemanticSearch will now use vector similarity.")
    return "\n".join(lines)


# ── Registration ──────────────────────────────────────────────────────────────

def register_index_tools() -> None:

    registry.register(
        name="IndexProject",
        description=(
            "Walk a project directory and build a SQLite symbol index: "
            "every function, class, method with its signature, docstring, and line number. "
            "Incremental -- only re-indexes changed files. Run this once per project."
        ),
        parameters={
            "type": "object",
            "properties": {
                "project_root": {"type": "string",
                                 "description": "Project root path (default: current dir)",
                                 "default": "."},
                "force":        {"type": "boolean",
                                 "description": "Re-index all files even if unchanged",
                                 "default": False},
            },
        },
        handler=_index_project,
        category="index",
    )

    registry.register(
        name="SymbolLookup",
        description=(
            "Find where a function, class, or method is defined. "
            "Returns file path, line number, signature, and docstring. "
            "Requires IndexProject to have been run first."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name":         {"type": "string",
                                 "description": "Symbol name to look up (exact or partial)"},
                "project_root": {"type": "string", "default": "."},
            },
            "required": ["name"],
        },
        handler=symbol_lookup,
        category="index",
    )

    registry.register(
        name="FindUsages",
        description=(
            "Find every file and line that references a symbol by name. "
            "Useful before refactoring -- see what breaks if you change something."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name":         {"type": "string",
                                 "description": "Symbol name to search for"},
                "project_root": {"type": "string", "default": "."},
            },
            "required": ["name"],
        },
        handler=find_usages,
        category="index",
    )

    registry.register(
        name="DependencyGraph",
        description=(
            "Show what a file imports AND what other files import it. "
            "Also lists all symbols defined in that file."
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_path":    {"type": "string",
                                 "description": "Relative or absolute path to the file"},
                "project_root": {"type": "string", "default": "."},
            },
            "required": ["file_path"],
        },
        handler=dependency_graph,
        category="index",
    )

    registry.register(
        name="SemanticSearch",
        description=(
            "Find code relevant to a natural-language query. "
            "Uses Ollama vector embeddings if EmbedProject has been run, "
            "otherwise falls back to FTS keyword search automatically."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query":        {"type": "string",
                                 "description": "What you're looking for in plain English"},
                "project_root": {"type": "string", "default": "."},
                "top_k":        {"type": "integer",
                                 "description": "Number of results to return", "default": 10},
            },
            "required": ["query"],
        },
        handler=semantic_search,
        category="index",
    )

    registry.register(
        name="EmbedProject",
        description=(
            "Generate Ollama vector embeddings for all indexed symbols to enable "
            "true semantic search. Requires: ollama pull nomic-embed-text. "
            "Run IndexProject first, then EmbedProject once."
        ),
        parameters={
            "type": "object",
            "properties": {
                "project_root": {"type": "string", "default": "."},
            },
        },
        handler=embed_project,
        category="index",
    )

# PG Index Manager & Janitor

A lightweight, framework-agnostic Python library designed for developers to audit database queries, surface runtime performance bottlenecks, and safely maintain PostgreSQL indexes.

Unlike heavy Application Performance Monitoring (APM) tools that require invasive database extensions (like HypoPG) or expensive SaaS subscriptions, this library operates entirely inside your application or via a clean CLI using native PostgreSQL capabilities.

> **DISCLAIMER:** This library is intended for development, staging, and testing environments only. It is **not recommended for production use** because `EXPLAIN ANALYZE` executes queries (which can impact live database performance) and the index dropping heuristics may be too aggressive for complex production workloads. Always test thoroughly in a non-production environment first.

---

## The Problem It Solves: "ORM Blindness"

Modern Object-Relational Mappers (ORMs) like Django or SQLAlchemy maximize developer productivity but hide the underlying SQL execution plan. A seemingly innocent line of Python code can silently trigger a **Sequential Scan (Full Table Scan)** across millions of rows, saturating server CPU and disk I/O.

Since Large Language Models (AI) cannot inspect your production database cardinality, table sizes, or live index catalogs, they cannot reliably predict query performance. This library bridges that gap by running live `EXPLAIN ANALYZE` inspections directly on the database engine.

---

## Key Features

### 1. Agnostic Performance Auditing
Intercepts raw SQL queries, recursively parses the native PostgreSQL execution tree, and catches performance anomalies (**Sequential Scans**) with exact millisecond runtimes.

- Parses `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` output
- Extracts **Shared Hit Blocks** (RAM) and **Shared Read Blocks** (disk)
- Logs every audit to `pg_query_audit.csv` with query fingerprinting to track performance regressions over time

### 2. Safe Janitor Mode (Interactive CLI)
Scans PostgreSQL system catalogs (`pg_stat_user_indexes`) to discover dead, unused indexes that are slowing down your `INSERT`/`UPDATE`/`DELETE` operations.

- Detects indexes with `idx_scan = 0` and `indisunique = FALSE`
- Interactive confirmation before dropping (`s` = yes, anything else = skip)
- Uses `DROP INDEX CONCURRENTLY` — **no table locks, zero downtime**

### 3. Zero-Dependency Architecture
Does not require root or superuser privileges on the database server. If you can connect to the database, you can run this library. Only requires:
- Python 3.8+
- `psycopg2` or `psycopg2-binary`

---

## Where Does It Live?

Because the core engine requires only a raw query string and a standard database connection, it is completely independent of your web framework.

### At the Driver Level (`psycopg2`)
Extend the native database cursor to automatically audit **100% of your application queries** (Django, FastAPI, Flask, or raw SQL).

### At the ORM Engine Level
Hook into global ORM events (e.g., SQLAlchemy's `before_cursor_execute`) to catch hidden query costs implicitly across all Services and Repositories — **zero business-code modification**.

---

## CLI Interface

When you run `run_cli(connection)`, you get an interactive menu:

========================================
PERSISTENT PG INDEX MANAGER CLI
========================================

1. Audit single SQL query efficiency
2. Scan and clean up dead indexes (Janitor Mode)
Type 'quit' at any prompt to exit.

=======================================


### Option 1: Audit a Query
- Paste any `SELECT` query (read-only, automatically sanitized)
- Returns: Execution time (ms), RAM hit blocks, disk read blocks
- Detects Sequential Scans vs Index Scans
- Logs results to `pg_query_audit.csv`

### Option 2: Janitor Mode
- Scans for unused indexes (`idx_scan = 0`)
- Lists each unused index with its parent table
- Asks for confirmation: `Drop index asynchronously (CONCURRENTLY)? [s/N]:`
  - Type `s` + Enter → drops safely in background
  - Any other input → skips

---

## Installation
```bash
pip install pg_idx_manager
```

Or install it in editable mode for development:

```bash
git clone https://github.com/pierpaolo1223/pg_index_manager.git
pip install -e .
```

## Getting Started & Testing Locally

### 1. Spin up a test database
Make sure you have a PostgreSQL instance running. Example connection string:

```text
dbname=testing_perf user=tester password=supersecretpassword host=localhost port=5432
```

### 2. Run the Core Agnostic Test
```bash
python tests/run_test.py
```

### 3. Run the ORM Integration Test
```bash
python tests/test_orm.py
```

## Security & Safety Notes

* **Read-only audit mode** — The CLI function `is_safe_query()` blocks dangerous keywords (`DROP TABLE`, `DELETE FROM`, `INSERT INTO`, etc.). Only `SELECT` queries are allowed for analysis.
* **Concurrent index drops** — Janitor mode uses `DROP INDEX CONCURRENTLY` to avoid blocking production writes.
* **No superuser required** — Works with standard PostgreSQL user permissions.

## CSV Audit Log Format

Every analyzed query is stored in `pg_query_audit.csv` with the following columns:


| Column | Description |
| :--- | :--- |
| **execution_date** | Timestamp of execution |
| **calling_function** | Auto-detected caller context |
| **execution_time_ms** | Query execution time in milliseconds |
| **scan_type** | `INDEX SCAN` or `SEQUENTIAL SCAN` |
| **ram_hit_blocks** | Shared Hit Blocks (from RAM) |
| **disk_read_blocks** | Shared Read Blocks (from disk) |
| **raw_sql** | Original SQL query string |

The library uses query fingerprinting (normalizing literals, parameters, and whitespace) to deduplicate and update the latest execution metrics for structurally identical queries.

## API Reference (Quick Start)

```python
import psycopg2
from pg_idx_manager import IndexManagerCore, run_cli

# Connect to your database
conn = psycopg2.connect("your_connection_string")

# Create manager instance
manager = IndexManagerCore(conn)

# Analyze a single query
anomalies, exec_time, io_stats = manager.analyze_query(
    "SELECT * FROM users WHERE email = 'user@example.com';"
)

# Launch interactive CLI
run_cli(conn)
```

## 📦 Package Structure (for contributors)

```text
pg_idx_manager/
├── __init__.py          # Module exports (IndexManagerCore, run_cli)
├── core.py              # IndexManagerCore class with explain parsing
├── cli.py               # Interactive CLI and safe query validation
└── pg_query_audit.csv   # Auto-generated audit log (created at runtime)

tests/
├── run_test.py          # Core functionality test with 10k records
└── test_orm.py          # SQLAlchemy integration example
```

## License

MIT License. Free to use and extend.

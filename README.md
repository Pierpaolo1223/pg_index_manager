# PG Index Manager & Janitor 🚀

A lightweight, framework-agnostic Python library designed for developers to audit database queries, surface runtime performance bottlenecks, and safely maintain PostgreSQL indexes.

Unlike heavy Application Performance Monitoring (APM) tools that require invasive database extensions (like HypoPG) or expensive SaaS subscriptions, this library operates entirely inside your application or via a clean CLI using native PostgreSQL capabilities.

## The Problem It Solves: "ORM Blindness"
Modern Object-Relational Mappers (ORMs) like Django or SQLAlchemy maximize developer productivity but hide the underlying SQL execution plan. A seemingly innocent line of Python code can silently trigger a **Sequential Scan (Full Table Scan)** across millions of rows, saturating server CPU and disk I/O.

Since Large Language Models (AI) cannot inspect your production database cardinality, table sizes, or live index catalogs, they cannot reliably predict query performance. This library bridges that gap by running live `EXPLAIN ANALYZE` inspections directly on the database engine.

## Key Features

1. **Agnostic Performance Auditing**: Intercepts raw SQL queries, recursively parses the native PostgreSQL execution tree, and catches performance anomalies (**Sequential Scans**) with exact millisecond runtimes.
2. **Safe Janitor Mode (Interactive CLI)**: Scans PostgreSQL system catalogs (`pg_stat_user_indexes`) to discover dead, unused indexes that are slowing down your `INSERT`/`UPDATE` mutations. It allows you to drop them interactively using `DROP INDEX CONCURRENTLY` without locking tables or risking production application downtime.
3. **Zero-Dependency Architecture**: Does not require root or superuser privileges on the database server. If you can connect to the database, you can run this library.

## Architectural Architecture: Where does it live?
Because the core engine requires only a raw query string and a standard database connection, it is completely independent of your web framework. You can integrate it at the lowest layer of your infrastructure:

* **At the Driver Level (`psycopg2`)**: By extending the native database cursor, you can automatically audit **100% of your application queries** (Django, FastAPI, Flask, or raw SQL) before they hit the wire.
* **At the ORM Engine Level**: Easily hooks into global ORM events (e.g., SQLAlchemy's `before_cursor_execute`) to catch hidden query costs implicitly across all Services and Repositories with zero business-code modification.

---

## Getting Started & Testing Locally 🧪

This repository includes a fully containerized testing environment to observe performance optimization in real-time.

### 1. Spin up the isolated test database
```bash
docker compose up -d
```

### 2. Install the library locally in editable mode
```bash
pip install -e .
```

### 3. Run the Core Agnostic Test
This script populates the database with **10,000 mock records**, executes an unindexed query, catches the Sequential Scan risk, and launches the persistent interactive CLI:
```bash
python tests/run_test.py
```

### 4. Run the ORM Integration Test
Observe how the library seamlessly intercepts real-time query metrics generated implicitly by SQLAlchemy ORM models:
```bash
python tests/test_orm.py
```

## License
MIT License. Free to use and extend.

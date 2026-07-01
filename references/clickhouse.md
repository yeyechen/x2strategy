# ClickHouse Data Extraction Guide

Read-on data extraction rules for academic dataset replication.  Connection
details are in ``.env``; the auto-generated schema catalog lives at
``paper2spec/resources/clickhouse_catalog.json``.

**IMPORTANT**: Do NOT attempt to connect to ClickHouse from the code-generation
environment (Claude, Copilot, etc.) — the host is on a private network and will
be unreachable.  During code generation, use these files for schema information:

- ``paper2spec/resources/clickhouse_catalog.json`` — all tables, columns, types, date ranges
- ``data_match_report.json`` — which tables provide each dataset for the current paper

Generate code that reads credentials from ``os.getenv()`` at runtime.  The
connection will work when the user runs ``strategy.py`` from their terminal.

---

## Connection

Credentials are read from ``.env`` via ``paper2spec.config.get_clickhouse_config()``.
Two ports are used because the project uses two protocols:

| Protocol | Port | Env var | Used by |
|----------|------|---------|---------|
| native TCP | 9000 | `CLICKHOUSE_PORT` | generated strategy code (`clickhouse_driver.Client`) |
| HTTP | 8123 | `CLICKHOUSE_HTTP_PORT` | schema discovery (`paper2spec.clickhouse.discover_schema`) |

Use the native TCP driver (port 9000) in generated strategy code:

```python
from clickhouse_driver import Client
client = Client(host=host, port=9000, user=user, password=pw, database=db)
rows = client.execute("SELECT 1")
```

The native driver returns proper Python ``None`` for NULL values — no ``\\N``
workaround needed.  HTTP (port 8123) is only used by the catalog discovery
script (`scripts/discover_clickhouse.py`), not by generated strategies.

---

## Schema Discovery (always before querying)

1. **List databases** — `SELECT name FROM system.databases WHERE name NOT IN ('system','information_schema','INFORMATION_SCHEMA')`
2. **List tables with size** — `SELECT database, name, engine, total_rows FROM system.tables WHERE database = 'X'`
3. **Get columns and comments** — `SELECT name, type, comment FROM system.columns WHERE database = 'X' AND table = 'Y' ORDER BY position`
4. **Understand the sort key** — `SELECT sorting_key, primary_key, partition_key FROM system.tables WHERE database = 'X' AND table = 'Y'`
5. **Check skipping indices** — `SELECT name, type_full, expr FROM system.data_skipping_indices WHERE database = 'X' AND table = 'Y'`
6. **Sample data** — `SELECT * FROM db.table LIMIT 5`
7. **Verify with EXPLAIN** — `EXPLAIN indexes = 1 SELECT ...` or `EXPLAIN ESTIMATE SELECT ...`

---

## Query Safety (CRITICAL — always apply)

Every query must carry explicit guards.  A single unbounded query can scan
billions of rows.

```sql
SELECT ...
FROM large_table
WHERE date_column >= '2020-01-01'    -- always filter on sort-key column
LIMIT 1000
SETTINGS max_execution_time = 30,
         max_rows_to_read = 1000000000,
         timeout_before_checking_execution_speed = 0
```

| Setting | Recommended | Effect |
|---------|-------------|--------|
| `max_execution_time` | 30 | Wall-clock limit (with `timeout_before_checking_execution_speed = 0`) |
| `max_rows_to_read` | 1e9 | Caps scanned rows |
| `max_result_rows` | 10000 | Caps returned rows |
| `result_overflow_mode` | `'break'` | Returns partial result when cap hit |

**Progressive exploration pattern:**

```sql
-- 1. Count first (cheap)
SELECT count() FROM table WHERE date = today();
-- 2. Sample (if count is reasonable)
SELECT * FROM table WHERE date = today() LIMIT 10;
-- 3. Full query with caps
SELECT ... FROM table WHERE date = today() LIMIT 1000
SETTINGS max_execution_time = 30, max_rows_to_read = 1000000000;
```

When things go wrong:
- **Timeout** → narrow time range, add sort-key filters
- **Memory error** → reduce GROUP BY cardinality, lower `LIMIT`

---

## Filter on ORDER BY Columns (CRITICAL)

Filtering on columns NOT in the sort key forces full scans.  Always include
prefix columns of the sort key in your WHERE clause.

```sql
-- Given ORDER BY (date, permno)
-- ❌ Full scan
SELECT * FROM crsp_dsf WHERE permno = 12345;
-- ✅ Uses primary index
SELECT * FROM crsp_dsf WHERE date >= '2020-01-01' AND date <= '2020-01-31';
SELECT * FROM crsp_dsf WHERE date = '2020-01-15' AND permno = 12345;
```

---

## JOIN Rules

### Filter before joining (CRITICAL)

```sql
-- ❌ Join entire tables, then filter
SELECT a.*, b.name FROM crsp_dsf a JOIN comp_funda b ON b.permno = a.permno
WHERE a.date >= '2020-01-01' AND b.fyear = 2020;

-- ✅ Filter in subqueries first
SELECT a.*, b.name
FROM (SELECT * FROM crsp_dsf WHERE date >= '2020-01-01') a
JOIN (SELECT * FROM comp_funda WHERE fyear = 2020) b ON b.permno = a.permno;
```

### Choose the right algorithm (CRITICAL)

| Algorithm | Best for |
|-----------|----------|
| `auto` (default) | General purpose — tries hash, falls back |
| `parallel_hash` | Small-to-medium tables (default since 24.11) |
| `direct` | Dictionary lookups — fastest, no hash table |
| `full_sorting_merge` | Tables already sorted on join key |
| `partial_merge` | Large tables, memory-constrained |

```sql
SET join_algorithm = 'partial_merge';
```

### Use ANY JOIN when one match is needed (HIGH)

```sql
-- ❌ Returns all matches, more memory
SELECT a.permno, b.sector FROM returns a LEFT JOIN companies b ON b.permno = a.permno;
-- ✅ Returns first match only
SELECT a.permno, b.sector FROM returns a LEFT ANY JOIN companies b ON b.permno = a.permno;
```

### Consider alternatives to JOIN (CRITICAL)

For repeated lookups to small dimension tables (e.g., company names), prefer
a pre-loaded dictionary over repeated JOINs.  For one-off analyses, JOIN is
fine.

### NULL handling in outer JOINs (MEDIUM)

`join_use_nulls = 0` (default): non-matching rows get default values (empty
string, 0) instead of NULL — uses less memory.

---

## Skipping Indices (HIGH)

For filters on columns NOT in the sort key, skipping indices avoid full scans.
Check what already exists with `system.data_skipping_indices`.

```sql
ALTER TABLE table ADD INDEX idx_col col_name TYPE bloom_filter GRANULARITY 4;
ALTER TABLE table MATERIALIZE INDEX idx_col;
-- Verify: EXPLAIN indexes = 1 SELECT * FROM table WHERE col_name = X;
```

| Index type | Best for |
|------------|----------|
| `bloom_filter` | Equality on high-cardinality columns |
| `minmax` | Range queries |
| `set(N)` | Low-cardinality columns (N unique values) |

---

## Data Types

### Use native types (CRITICAL)

| Data | Use | Avoid |
|------|-----|-------|
| IDs, permnos | UInt32/UInt64 | String |
| Returns, ratios | Float64 | String |
| Prices (absolute value) | Float64 | Decimal |
| Dates | Date or Date32 | DateTime, String |
| Counts | UInt8/16/32 (smallest that fits) | Int64, String |
| Categories | Enum8 or LowCardinality(String) | String |

### Minimize bit-width (HIGH)

Pick the smallest numeric range that fits.  Example: `year` → `UInt16` (0-65535).

| Type | Range | Bytes |
|------|-------|-------|
| UInt8 | 0–255 | 1 |
| UInt16 | 0–65,535 | 2 |
| UInt32 | 0–4.3B | 4 |
| Float64 | IEEE double | 8 |

### LowCardinality (HIGH)

Use `LowCardinality(String)` for columns with <10K unique values (exchange
codes, share codes, industry classifications).  Verify with `SELECT uniq(col)`.

### Avoid Nullable unless semantic (HIGH)

Nullable doubles storage (extra UInt8 column).  Use `DEFAULT` values instead:
`''` for strings, `0` for numerics.  Only use Nullable when NULL has a distinct
semantic meaning (e.g., `deleted_at` — NULL = not deleted).

---

## Data Catalog

The auto-generated catalog at ``paper2spec/resources/clickhouse_catalog.json``
lists every database, table, column, row count, and date range.  Refresh with:

```bash
python scripts/discover_clickhouse.py --refresh
```

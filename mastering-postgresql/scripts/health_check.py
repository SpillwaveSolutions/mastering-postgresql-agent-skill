#!/usr/bin/env python3
"""
Script: health_check.py
Purpose: Monitor PostgreSQL database health, index usage, and performance
Usage: python health_check.py --host localhost --dbname mydb

Checks:
- Connection health
- Extension status
- Index usage and efficiency
- Table bloat
- Slow queries (via pg_stat_statements)
- Connection count
"""

import argparse
import sys
from typing import List, Dict, Any

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("Error: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


def connect(host: str, port: int, dbname: str, user: str, password: str):
    """Create database connection with dict cursor."""
    return psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        cursor_factory=RealDictCursor
    )


def check_extensions(cur) -> List[Dict]:
    """Check installed extensions."""
    cur.execute("""
        SELECT extname, extversion 
        FROM pg_extension 
        ORDER BY extname
    """)
    return cur.fetchall()


def check_database_size(cur, dbname: str) -> Dict:
    """Get database size information."""
    cur.execute("""
        SELECT 
            pg_size_pretty(pg_database_size(%s)) AS database_size,
            pg_database_size(%s) AS size_bytes
    """, (dbname, dbname))
    return cur.fetchone()


def check_table_sizes(cur, limit: int = 10) -> List[Dict]:
    """Get largest tables."""
    cur.execute("""
        SELECT 
            schemaname,
            relname AS table_name,
            n_live_tup AS row_count,
            pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
            pg_size_pretty(pg_relation_size(relid)) AS table_size,
            pg_size_pretty(pg_indexes_size(relid)) AS index_size
        FROM pg_stat_user_tables
        ORDER BY pg_total_relation_size(relid) DESC
        LIMIT %s
    """, (limit,))
    return cur.fetchall()


def check_index_usage(cur) -> List[Dict]:
    """Check index usage statistics."""
    cur.execute("""
        SELECT 
            schemaname,
            relname AS table_name,
            indexrelname AS index_name,
            idx_scan AS index_scans,
            idx_tup_read AS tuples_read,
            idx_tup_fetch AS tuples_fetched,
            pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
        FROM pg_stat_user_indexes
        ORDER BY idx_scan DESC
        LIMIT 20
    """)
    return cur.fetchall()


def check_unused_indexes(cur) -> List[Dict]:
    """Find unused indexes (candidates for removal)."""
    cur.execute("""
        SELECT 
            schemaname,
            relname AS table_name,
            indexrelname AS index_name,
            idx_scan AS scans,
            pg_size_pretty(pg_relation_size(indexrelid)) AS size
        FROM pg_stat_user_indexes
        WHERE idx_scan = 0
        AND indexrelname NOT LIKE '%_pkey'
        ORDER BY pg_relation_size(indexrelid) DESC
    """)
    return cur.fetchall()


def check_missing_indexes(cur) -> List[Dict]:
    """Find tables with high sequential scan ratios (may need indexes)."""
    cur.execute("""
        SELECT 
            schemaname,
            relname AS table_name,
            seq_scan,
            idx_scan,
            n_live_tup AS row_count,
            CASE WHEN seq_scan + idx_scan > 0 
                THEN round(100.0 * seq_scan / (seq_scan + idx_scan), 1)
                ELSE 0 
            END AS seq_scan_pct
        FROM pg_stat_user_tables
        WHERE n_live_tup > 1000
        AND seq_scan > idx_scan
        ORDER BY seq_scan DESC
        LIMIT 10
    """)
    return cur.fetchall()


def check_table_bloat(cur) -> List[Dict]:
    """Check for table bloat (dead tuples)."""
    cur.execute("""
        SELECT 
            schemaname,
            relname AS table_name,
            n_live_tup AS live_tuples,
            n_dead_tup AS dead_tuples,
            CASE WHEN n_live_tup > 0 
                THEN round(100.0 * n_dead_tup / n_live_tup, 1)
                ELSE 0 
            END AS dead_pct,
            last_vacuum,
            last_autovacuum,
            last_analyze
        FROM pg_stat_user_tables
        WHERE n_dead_tup > 1000
        ORDER BY n_dead_tup DESC
        LIMIT 10
    """)
    return cur.fetchall()


def check_connections(cur) -> Dict:
    """Check connection statistics."""
    cur.execute("""
        SELECT 
            (SELECT count(*) FROM pg_stat_activity) AS total_connections,
            (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') AS active,
            (SELECT count(*) FROM pg_stat_activity WHERE state = 'idle') AS idle,
            (SELECT count(*) FROM pg_stat_activity WHERE state = 'idle in transaction') AS idle_in_transaction,
            (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_connections
    """)
    return cur.fetchone()


def check_slow_queries(cur, limit: int = 10) -> List[Dict]:
    """Get slowest queries from pg_stat_statements (if available)."""
    try:
        cur.execute("""
            SELECT 
                substring(query, 1, 80) AS query_preview,
                calls,
                round(total_exec_time::numeric, 2) AS total_time_ms,
                round(mean_exec_time::numeric, 2) AS avg_time_ms,
                round(stddev_exec_time::numeric, 2) AS stddev_ms,
                rows
            FROM pg_stat_statements
            ORDER BY total_exec_time DESC
            LIMIT %s
        """, (limit,))
        return cur.fetchall()
    except psycopg2.Error:
        return []


def check_locks(cur) -> List[Dict]:
    """Check for blocking queries."""
    cur.execute("""
        SELECT 
            blocked.pid AS blocked_pid,
            blocked.query AS blocked_query,
            blocking.pid AS blocking_pid,
            blocking.query AS blocking_query,
            blocked.wait_event_type,
            blocked.wait_event
        FROM pg_stat_activity blocked
        JOIN pg_stat_activity blocking ON blocking.pid = ANY(pg_blocking_pids(blocked.pid))
        WHERE blocked.pid != blocking.pid
    """)
    return cur.fetchall()


def check_replication_lag(cur) -> List[Dict]:
    """Check replication status (if replicas exist)."""
    cur.execute("""
        SELECT 
            client_addr,
            state,
            sent_lsn,
            write_lsn,
            flush_lsn,
            replay_lsn,
            pg_size_pretty(pg_wal_lsn_diff(sent_lsn, replay_lsn)) AS replication_lag
        FROM pg_stat_replication
    """)
    return cur.fetchall()


def print_section(title: str):
    """Print section header."""
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)


def print_table(rows: List[Dict], columns: List[str] = None):
    """Print rows as formatted table."""
    if not rows:
        print("  No data")
        return
    
    if columns is None:
        columns = list(rows[0].keys())
    
    # Calculate column widths
    widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            val = str(row.get(col, ''))
            widths[col] = max(widths[col], len(val))
    
    # Print header
    header = " | ".join(col.ljust(widths[col]) for col in columns)
    print(f"  {header}")
    print(f"  {'-' * len(header)}")
    
    # Print rows
    for row in rows:
        line = " | ".join(str(row.get(col, '')).ljust(widths[col]) for col in columns)
        print(f"  {line}")


def main():
    parser = argparse.ArgumentParser(
        description="PostgreSQL health check and monitoring"
    )
    parser.add_argument("--host", default="localhost", help="Database host")
    parser.add_argument("--port", type=int, default=5432, help="Database port")
    parser.add_argument("--dbname", default="postgres", help="Database name")
    parser.add_argument("--user", default="postgres", help="Database user")
    parser.add_argument("--password", default="", help="Database password")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show more details")
    args = parser.parse_args()

    print(f"PostgreSQL Health Check")
    print(f"Host: {args.host}:{args.port}/{args.dbname}")
    
    try:
        conn = connect(args.host, args.port, args.dbname, args.user, args.password)
    except psycopg2.Error as e:
        print(f"\n❌ Connection FAILED: {e}")
        sys.exit(1)
    
    print(f"✓ Connection successful")
    
    cur = conn.cursor()
    issues = []
    
    # Extensions
    print_section("Extensions")
    extensions = check_extensions(cur)
    for ext in extensions:
        print(f"  ✓ {ext['extname']} ({ext['extversion']})")
    
    # Check for recommended extensions
    ext_names = {e['extname'] for e in extensions}
    if 'vector' not in ext_names:
        issues.append("pgvector extension not installed")
    if 'pg_trgm' not in ext_names:
        issues.append("pg_trgm extension not installed")
    if 'pg_stat_statements' not in ext_names:
        issues.append("pg_stat_statements not enabled (recommended for monitoring)")
    
    # Database size
    print_section("Database Size")
    size_info = check_database_size(cur, args.dbname)
    print(f"  Total size: {size_info['database_size']}")
    
    # Table sizes
    print_section("Largest Tables")
    tables = check_table_sizes(cur)
    print_table(tables, ['table_name', 'row_count', 'total_size', 'table_size', 'index_size'])
    
    # Index usage
    print_section("Index Usage (Top 20)")
    indexes = check_index_usage(cur)
    print_table(indexes, ['table_name', 'index_name', 'index_scans', 'index_size'])
    
    # Unused indexes
    print_section("Unused Indexes (Consider Removing)")
    unused = check_unused_indexes(cur)
    if unused:
        print_table(unused, ['table_name', 'index_name', 'scans', 'size'])
        issues.append(f"{len(unused)} unused indexes found")
    else:
        print("  ✓ No unused indexes found")
    
    # Missing indexes
    print_section("Tables Needing Indexes (High Seq Scan %)")
    missing = check_missing_indexes(cur)
    if missing:
        print_table(missing, ['table_name', 'seq_scan', 'idx_scan', 'row_count', 'seq_scan_pct'])
        issues.append(f"{len(missing)} tables with high sequential scan ratio")
    else:
        print("  ✓ All tables have good index coverage")
    
    # Table bloat
    print_section("Table Bloat (Dead Tuples)")
    bloat = check_table_bloat(cur)
    if bloat:
        print_table(bloat, ['table_name', 'live_tuples', 'dead_tuples', 'dead_pct', 'last_autovacuum'])
        for row in bloat:
            if row['dead_pct'] and row['dead_pct'] > 20:
                issues.append(f"Table {row['table_name']} has {row['dead_pct']}% dead tuples")
    else:
        print("  ✓ No significant bloat detected")
    
    # Connections
    print_section("Connections")
    conn_stats = check_connections(cur)
    print(f"  Total: {conn_stats['total_connections']} / {conn_stats['max_connections']} max")
    print(f"  Active: {conn_stats['active']}")
    print(f"  Idle: {conn_stats['idle']}")
    print(f"  Idle in transaction: {conn_stats['idle_in_transaction']}")
    
    if conn_stats['idle_in_transaction'] > 5:
        issues.append(f"{conn_stats['idle_in_transaction']} connections idle in transaction")
    
    usage_pct = 100 * conn_stats['total_connections'] / conn_stats['max_connections']
    if usage_pct > 80:
        issues.append(f"Connection usage at {usage_pct:.0f}%")
    
    # Slow queries
    print_section("Slow Queries (via pg_stat_statements)")
    slow = check_slow_queries(cur)
    if slow:
        print_table(slow, ['query_preview', 'calls', 'total_time_ms', 'avg_time_ms'])
    else:
        print("  pg_stat_statements not available or no queries recorded")
    
    # Locks
    print_section("Blocking Queries")
    locks = check_locks(cur)
    if locks:
        print_table(locks, ['blocked_pid', 'blocking_pid', 'wait_event'])
        issues.append(f"{len(locks)} blocking locks detected")
    else:
        print("  ✓ No blocking queries")
    
    # Replication
    if args.verbose:
        print_section("Replication Status")
        replication = check_replication_lag(cur)
        if replication:
            print_table(replication, ['client_addr', 'state', 'replication_lag'])
        else:
            print("  No replicas connected")
    
    # Summary
    print_section("Summary")
    if issues:
        print(f"  ⚠ {len(issues)} issue(s) found:")
        for issue in issues:
            print(f"    - {issue}")
    else:
        print("  ✓ No issues detected")
    
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()

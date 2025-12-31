#!/usr/bin/env python3
"""
Script: setup_extensions.py
Purpose: Install and verify PostgreSQL extensions for search/vector workloads
Usage: python setup_extensions.py --host localhost --port 5432 --dbname mydb --user postgres

This script installs pgvector, pg_trgm, and other search-related extensions,
then verifies they are working correctly.
"""

import argparse
import sys

try:
    import psycopg2
    from psycopg2 import sql
except ImportError:
    print("Error: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


EXTENSIONS = [
    ("vector", "pgvector for vector similarity search"),
    ("pg_trgm", "Trigram similarity for fuzzy search"),
    ("uuid-ossp", "UUID generation functions"),
]

OPTIONAL_EXTENSIONS = [
    ("pg_stat_statements", "Query statistics (requires shared_preload_libraries)"),
    ("pg_search", "BM25 search (ParadeDB only)"),
]


def connect(host: str, port: int, dbname: str, user: str, password: str):
    """Create database connection."""
    return psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password
    )


def get_installed_extensions(cur) -> dict:
    """Get currently installed extensions with versions."""
    cur.execute("SELECT extname, extversion FROM pg_extension")
    return {row[0]: row[1] for row in cur.fetchall()}


def get_available_extensions(cur) -> set:
    """Get extensions available for installation."""
    cur.execute("SELECT name FROM pg_available_extensions")
    return {row[0] for row in cur.fetchall()}


def install_extension(cur, name: str) -> bool:
    """Install an extension. Returns True if successful."""
    try:
        cur.execute(sql.SQL("CREATE EXTENSION IF NOT EXISTS {}").format(
            sql.Identifier(name)
        ))
        return True
    except psycopg2.Error as e:
        print(f"  Warning: Could not install {name}: {e.pgerror.strip()}")
        return False


def verify_vector_extension(cur) -> bool:
    """Verify pgvector is working correctly."""
    try:
        cur.execute("SELECT '[1,2,3]'::vector <=> '[4,5,6]'::vector AS distance")
        result = cur.fetchone()[0]
        return abs(result - 5.196) < 0.01  # sqrt(9+9+9)
    except Exception:
        return False


def verify_trgm_extension(cur) -> bool:
    """Verify pg_trgm is working correctly."""
    try:
        cur.execute("SELECT similarity('PostgreSQL', 'Postgres')")
        result = cur.fetchone()[0]
        return result > 0.5
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Install and verify PostgreSQL extensions for search/vector workloads"
    )
    parser.add_argument("--host", default="localhost", help="Database host")
    parser.add_argument("--port", type=int, default=5432, help="Database port")
    parser.add_argument("--dbname", default="postgres", help="Database name")
    parser.add_argument("--user", default="postgres", help="Database user")
    parser.add_argument("--password", default="", help="Database password")
    parser.add_argument("--include-optional", action="store_true", 
                        help="Try to install optional extensions")
    args = parser.parse_args()

    print(f"Connecting to {args.host}:{args.port}/{args.dbname}...")
    
    try:
        conn = connect(args.host, args.port, args.dbname, args.user, args.password)
        conn.autocommit = True
    except psycopg2.Error as e:
        print(f"Error: Could not connect to database: {e}")
        sys.exit(1)

    cur = conn.cursor()
    
    # Get current state
    installed = get_installed_extensions(cur)
    available = get_available_extensions(cur)
    
    print(f"\nCurrently installed extensions: {len(installed)}")
    for name, version in installed.items():
        print(f"  - {name} ({version})")
    
    # Install required extensions
    print("\n--- Installing Required Extensions ---")
    extensions_to_install = EXTENSIONS
    if args.include_optional:
        extensions_to_install = EXTENSIONS + OPTIONAL_EXTENSIONS
    
    results = {"installed": [], "skipped": [], "failed": []}
    
    for ext_name, description in extensions_to_install:
        print(f"\n{ext_name}: {description}")
        
        if ext_name in installed:
            print(f"  Already installed (v{installed[ext_name]})")
            results["skipped"].append(ext_name)
        elif ext_name not in available:
            print(f"  Not available on this PostgreSQL installation")
            results["failed"].append(ext_name)
        else:
            if install_extension(cur, ext_name):
                print(f"  Installed successfully")
                results["installed"].append(ext_name)
            else:
                results["failed"].append(ext_name)
    
    # Verify critical extensions
    print("\n--- Verification ---")
    
    if "vector" in get_installed_extensions(cur):
        if verify_vector_extension(cur):
            print("✓ pgvector: Working correctly")
        else:
            print("✗ pgvector: Verification failed")
    
    if "pg_trgm" in get_installed_extensions(cur):
        if verify_trgm_extension(cur):
            print("✓ pg_trgm: Working correctly")
        else:
            print("✗ pg_trgm: Verification failed")
    
    # Summary
    print("\n--- Summary ---")
    print(f"Installed: {len(results['installed'])} ({', '.join(results['installed']) or 'none'})")
    print(f"Skipped (already installed): {len(results['skipped'])}")
    print(f"Failed/Unavailable: {len(results['failed'])} ({', '.join(results['failed']) or 'none'})")
    
    cur.close()
    conn.close()
    
    # Exit with error if required extensions failed
    required_names = [e[0] for e in EXTENSIONS]
    failed_required = [f for f in results["failed"] if f in required_names]
    if failed_required:
        print(f"\nError: Required extensions could not be installed: {failed_required}")
        sys.exit(1)
    
    print("\nExtension setup complete!")


if __name__ == "__main__":
    main()

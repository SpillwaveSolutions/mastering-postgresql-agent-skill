#!/usr/bin/env python3
"""
Shared database utilities for PostgreSQL skill scripts.

This module provides common connection patterns and argument parsing
to reduce duplication across scripts.
"""

import argparse
import sys
from contextlib import contextmanager
from typing import Optional

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("Error: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


def get_connection_args(parser: Optional[argparse.ArgumentParser] = None) -> argparse.ArgumentParser:
    """
    Add standard database connection arguments to an argument parser.
    
    Args:
        parser: Existing parser to add arguments to, or None to create new one
        
    Returns:
        ArgumentParser with database connection arguments added
    """
    if parser is None:
        parser = argparse.ArgumentParser()
    
    parser.add_argument('--host', default='localhost', help='Database host')
    parser.add_argument('--port', type=int, default=5432, help='Database port')
    parser.add_argument('--dbname', default='postgres', help='Database name')
    parser.add_argument('--user', default='postgres', help='Database user')
    parser.add_argument('--password', default='', help='Database password')
    
    return parser


def connect(host: str, port: int, dbname: str, user: str, password: str):
    """
    Create a database connection with standard settings.
    
    Args:
        host: Database host
        port: Database port
        dbname: Database name
        user: Database user
        password: Database password
        
    Returns:
        psycopg2 connection object
    """
    return psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password
    )


def connect_from_args(args: argparse.Namespace):
    """
    Create a database connection from parsed arguments.
    
    Args:
        args: Parsed argparse namespace with connection parameters
        
    Returns:
        psycopg2 connection object
    """
    return connect(
        host=args.host,
        port=args.port,
        dbname=args.dbname,
        user=args.user,
        password=args.password
    )


@contextmanager
def get_cursor(conn, commit: bool = True, dict_cursor: bool = True):
    """
    Context manager for database cursor with automatic commit/rollback.
    
    Args:
        conn: Database connection
        commit: Whether to commit on success (default True)
        dict_cursor: Use RealDictCursor for dict-like rows (default True)
        
    Yields:
        Database cursor
    """
    cursor_factory = RealDictCursor if dict_cursor else None
    try:
        with conn.cursor(cursor_factory=cursor_factory) as cur:
            yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise


def test_connection(conn) -> bool:
    """
    Test that a database connection is working.
    
    Args:
        conn: Database connection to test
        
    Returns:
        True if connection is working
    """
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone()[0] == 1
    except Exception:
        return False


def get_postgres_version(conn) -> str:
    """
    Get the PostgreSQL server version.
    
    Args:
        conn: Database connection
        
    Returns:
        Version string (e.g., "16.2")
    """
    with conn.cursor() as cur:
        cur.execute("SHOW server_version")
        return cur.fetchone()[0]

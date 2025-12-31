#!/usr/bin/env python3
"""
Script: bulk_operations.py
Purpose: Efficient bulk insert patterns for PostgreSQL with vectors
Usage: python bulk_operations.py --host localhost --dbname mydb --demo

Demonstrates different bulk insert strategies:
1. execute_values (psycopg2) - Good balance of speed and flexibility
2. COPY protocol - Fastest for large imports
3. Batch inserts - Simple but slower

Includes vector data handling for pgvector columns.
"""

import argparse
import sys
import time
import random
import json
from typing import List, Tuple, Optional

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("Error: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

try:
    from pgvector.psycopg2 import register_vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False
    print("Warning: pgvector Python package not installed. Vector operations limited.")
    print("Run: pip install pgvector")


def generate_sample_documents(count: int, with_vectors: bool = False) -> List[Tuple]:
    """Generate sample document data for testing."""
    documents = []
    
    categories = ["tutorial", "reference", "guide", "article", "documentation"]
    tags_pool = ["python", "postgresql", "database", "sql", "performance", 
                 "indexing", "search", "vectors", "ai", "ml"]
    
    for i in range(count):
        title = f"Document {i+1}: {random.choice(['Guide to', 'Introduction to', 'Advanced'])} {random.choice(tags_pool).title()}"
        content = f"This is the content for document {i+1}. " * random.randint(5, 20)
        metadata = json.dumps({
            "type": random.choice(categories),
            "priority": random.randint(1, 5)
        })
        tags = random.sample(tags_pool, random.randint(1, 4))
        
        if with_vectors:
            # Generate random 1536-dim vector (simulating embeddings)
            embedding = [random.uniform(-1, 1) for _ in range(1536)]
            documents.append((title, content, metadata, tags, embedding))
        else:
            documents.append((title, content, metadata, tags))
    
    return documents


def bulk_insert_execute_values(
    conn, 
    data: List[Tuple], 
    with_vectors: bool = False,
    batch_size: int = 1000
) -> float:
    """
    Insert using execute_values - recommended for most use cases.
    
    Pros: Good performance, supports complex types, ON CONFLICT support
    Cons: Slightly slower than COPY for very large imports
    """
    start = time.time()
    
    with conn.cursor() as cur:
        if with_vectors:
            # With vector column
            execute_values(
                cur,
                """INSERT INTO documents (title, content, metadata, tags, embedding)
                   VALUES %s
                   ON CONFLICT DO NOTHING""",
                data,
                template="(%s, %s, %s::jsonb, %s::text[], %s::vector)",
                page_size=batch_size
            )
        else:
            # Without vector column
            execute_values(
                cur,
                """INSERT INTO documents (title, content, metadata, tags)
                   VALUES %s
                   ON CONFLICT DO NOTHING""",
                data,
                template="(%s, %s, %s::jsonb, %s::text[])",
                page_size=batch_size
            )
    
    conn.commit()
    return time.time() - start


def bulk_insert_copy(
    conn,
    data: List[Tuple],
    with_vectors: bool = False
) -> float:
    """
    Insert using COPY protocol - fastest method.
    
    Pros: Maximum speed for large imports
    Cons: No ON CONFLICT, requires specific formatting
    """
    from io import StringIO
    
    start = time.time()
    
    # Format data for COPY
    buffer = StringIO()
    for row in data:
        if with_vectors:
            title, content, metadata, tags, embedding = row
            # Format: title, content, metadata, tags, embedding
            tags_str = "{" + ",".join(f'"{t}"' for t in tags) + "}"
            embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
            line = f"{title}\t{content}\t{metadata}\t{tags_str}\t{embedding_str}\n"
        else:
            title, content, metadata, tags = row
            tags_str = "{" + ",".join(f'"{t}"' for t in tags) + "}"
            line = f"{title}\t{content}\t{metadata}\t{tags_str}\n"
        buffer.write(line)
    
    buffer.seek(0)
    
    with conn.cursor() as cur:
        if with_vectors:
            cur.copy_expert(
                """COPY documents (title, content, metadata, tags, embedding) 
                   FROM STDIN WITH (FORMAT text)""",
                buffer
            )
        else:
            cur.copy_expert(
                """COPY documents (title, content, metadata, tags) 
                   FROM STDIN WITH (FORMAT text)""",
                buffer
            )
    
    conn.commit()
    return time.time() - start


def bulk_insert_batch(
    conn,
    data: List[Tuple],
    with_vectors: bool = False,
    batch_size: int = 100
) -> float:
    """
    Insert using batched executemany - simple but slower.
    
    Pros: Simple, works everywhere
    Cons: Slowest method, many round trips
    """
    start = time.time()
    
    with conn.cursor() as cur:
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            
            if with_vectors:
                cur.executemany(
                    """INSERT INTO documents (title, content, metadata, tags, embedding)
                       VALUES (%s, %s, %s::jsonb, %s::text[], %s::vector)
                       ON CONFLICT DO NOTHING""",
                    batch
                )
            else:
                cur.executemany(
                    """INSERT INTO documents (title, content, metadata, tags)
                       VALUES (%s, %s, %s::jsonb, %s::text[])
                       ON CONFLICT DO NOTHING""",
                    batch
                )
            
            conn.commit()
    
    return time.time() - start


def clear_documents(conn):
    """Clear all documents from the table."""
    with conn.cursor() as cur:
        cur.execute("TRUNCATE documents RESTART IDENTITY")
    conn.commit()


def count_documents(conn) -> int:
    """Get document count."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM documents")
        return cur.fetchone()[0]


def run_benchmark(conn, count: int = 1000, with_vectors: bool = False):
    """Run benchmark comparing insert methods."""
    print(f"\n=== Benchmark: {count} rows {'with' if with_vectors else 'without'} vectors ===\n")
    
    # Generate test data
    print(f"Generating {count} sample documents...")
    data = generate_sample_documents(count, with_vectors)
    print(f"  Data generated ({len(data)} rows)")
    
    results = {}
    
    # Test execute_values
    print("\n1. execute_values method:")
    clear_documents(conn)
    elapsed = bulk_insert_execute_values(conn, data, with_vectors)
    results["execute_values"] = elapsed
    print(f"   Time: {elapsed:.3f}s ({count/elapsed:.0f} rows/sec)")
    print(f"   Rows inserted: {count_documents(conn)}")
    
    # Test COPY (only without vectors for simplicity)
    if not with_vectors:
        print("\n2. COPY method:")
        clear_documents(conn)
        elapsed = bulk_insert_copy(conn, data, with_vectors)
        results["copy"] = elapsed
        print(f"   Time: {elapsed:.3f}s ({count/elapsed:.0f} rows/sec)")
        print(f"   Rows inserted: {count_documents(conn)}")
    
    # Test batch executemany (smaller sample for speed)
    batch_count = min(count, 500)
    batch_data = data[:batch_count]
    print(f"\n3. Batch executemany method ({batch_count} rows):")
    clear_documents(conn)
    elapsed = bulk_insert_batch(conn, batch_data, with_vectors)
    results["batch"] = elapsed
    print(f"   Time: {elapsed:.3f}s ({batch_count/elapsed:.0f} rows/sec)")
    print(f"   Rows inserted: {count_documents(conn)}")
    
    # Summary
    print("\n=== Summary ===")
    fastest = min(results.items(), key=lambda x: x[1])
    print(f"Fastest method: {fastest[0]}")
    print("\nRecommendation:")
    print("  - Use execute_values for most cases (good speed, flexible)")
    print("  - Use COPY for large imports without conflicts")
    print("  - Avoid executemany for bulk operations")


def main():
    parser = argparse.ArgumentParser(
        description="Demonstrate bulk insert patterns for PostgreSQL"
    )
    parser.add_argument("--host", default="localhost", help="Database host")
    parser.add_argument("--port", type=int, default=5432, help="Database port")
    parser.add_argument("--dbname", default="postgres", help="Database name")
    parser.add_argument("--user", default="postgres", help="Database user")
    parser.add_argument("--password", default="", help="Database password")
    parser.add_argument("--demo", action="store_true", help="Run benchmark demo")
    parser.add_argument("--count", type=int, default=1000, help="Number of rows for demo")
    parser.add_argument("--with-vectors", action="store_true", help="Include vector data")
    args = parser.parse_args()

    print(f"Connecting to {args.host}:{args.port}/{args.dbname}...")
    
    try:
        conn = psycopg2.connect(
            host=args.host,
            port=args.port,
            dbname=args.dbname,
            user=args.user,
            password=args.password
        )
    except psycopg2.Error as e:
        print(f"Error: Could not connect: {e}")
        sys.exit(1)

    # Register vector type if available
    if HAS_PGVECTOR:
        try:
            register_vector(conn)
            print("pgvector type registered")
        except Exception as e:
            print(f"Warning: Could not register vector type: {e}")

    if args.demo:
        run_benchmark(conn, args.count, args.with_vectors)
    else:
        print("\nUsage: Run with --demo to see benchmark")
        print("       Run with --demo --with-vectors for vector insert benchmark")
    
    conn.close()


if __name__ == "__main__":
    main()

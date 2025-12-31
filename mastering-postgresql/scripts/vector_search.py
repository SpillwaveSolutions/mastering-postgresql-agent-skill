#!/usr/bin/env python3
"""
Script: vector_search.py
Purpose: pgvector query helpers and examples
Usage: python vector_search.py --host localhost --dbname mydb --demo

Demonstrates:
- Vector similarity search
- Hybrid search (text + vectors)
- Filtered vector search
- Index tuning queries
"""

import argparse
import sys
import time
import random
from typing import List, Dict, Optional

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("Error: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

try:
    from pgvector.psycopg2 import register_vector
    import numpy as np
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False
    print("Warning: pgvector or numpy not installed.")
    print("Run: pip install pgvector numpy")


def connect(host: str, port: int, dbname: str, user: str, password: str):
    """Create database connection."""
    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        cursor_factory=RealDictCursor
    )
    if HAS_DEPS:
        register_vector(conn)
    return conn


def generate_random_vector(dims: int = 1536) -> List[float]:
    """Generate a random normalized vector."""
    if HAS_DEPS:
        vec = np.random.randn(dims)
        vec = vec / np.linalg.norm(vec)  # Normalize
        return vec.tolist()
    else:
        return [random.uniform(-1, 1) for _ in range(dims)]


def similarity_search(
    conn,
    embedding: List[float],
    limit: int = 10,
    distance_type: str = "cosine"
) -> List[Dict]:
    """
    Basic vector similarity search.
    
    Args:
        embedding: Query vector
        limit: Number of results
        distance_type: 'cosine', 'l2', or 'inner_product'
    """
    operators = {
        "cosine": "<=>",
        "l2": "<->",
        "inner_product": "<#>"
    }
    op = operators.get(distance_type, "<=>")
    
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, title, 
                   embedding {op} %s::vector AS distance,
                   1 - (embedding {op} %s::vector) AS similarity
            FROM documents
            WHERE embedding IS NOT NULL
            ORDER BY embedding {op} %s::vector
            LIMIT %s
        """, (embedding, embedding, embedding, limit))
        return cur.fetchall()


def filtered_similarity_search(
    conn,
    embedding: List[float],
    tags: List[str] = None,
    metadata_filter: Dict = None,
    limit: int = 10
) -> List[Dict]:
    """
    Vector search with pre-filtering.
    
    Args:
        embedding: Query vector
        tags: Filter by tags (any match)
        metadata_filter: JSONB containment filter
        limit: Number of results
    """
    conditions = ["embedding IS NOT NULL"]
    params = [embedding, embedding]
    
    if tags:
        conditions.append("tags && %s::text[]")
        params.append(tags)
    
    if metadata_filter:
        conditions.append("metadata @> %s::jsonb")
        params.append(psycopg2.extras.Json(metadata_filter))
    
    params.append(limit)
    where_clause = " AND ".join(conditions)
    
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, title, tags, metadata,
                   embedding <=> %s::vector AS distance
            FROM documents
            WHERE {where_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, params)
        return cur.fetchall()


def hybrid_search(
    conn,
    query_text: str,
    query_embedding: List[float],
    text_weight: float = 0.3,
    vector_weight: float = 0.7,
    limit: int = 20
) -> List[Dict]:
    """
    Combine full-text search with vector similarity.
    
    Uses Reciprocal Rank Fusion (RRF) for score combination.
    """
    with conn.cursor() as cur:
        cur.execute("""
            WITH text_search AS (
                SELECT id, 
                       ROW_NUMBER() OVER (ORDER BY ts_rank(search_vector, query) DESC) AS text_rank
                FROM documents, websearch_to_tsquery('english', %s) query
                WHERE search_vector @@ query
                LIMIT 50
            ),
            vector_search AS (
                SELECT id,
                       ROW_NUMBER() OVER (ORDER BY embedding <=> %s::vector) AS vector_rank
                FROM documents
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT 50
            ),
            combined AS (
                SELECT 
                    COALESCE(t.id, v.id) AS id,
                    COALESCE(1.0 / (60 + t.text_rank), 0) * %s AS text_score,
                    COALESCE(1.0 / (60 + v.vector_rank), 0) * %s AS vector_score
                FROM text_search t
                FULL OUTER JOIN vector_search v ON t.id = v.id
            )
            SELECT d.id, d.title, d.content,
                   c.text_score, c.vector_score,
                   c.text_score + c.vector_score AS combined_score
            FROM combined c
            JOIN documents d ON c.id = d.id
            ORDER BY combined_score DESC
            LIMIT %s
        """, (query_text, query_embedding, query_embedding, 
              text_weight, vector_weight, limit))
        return cur.fetchall()


def check_index_stats(conn, table_name: str = "documents") -> Dict:
    """Get vector index statistics."""
    with conn.cursor() as cur:
        # Check for vector indexes
        cur.execute("""
            SELECT indexname, indexdef,
                   pg_size_pretty(pg_relation_size(indexname::regclass)) AS size
            FROM pg_indexes
            WHERE tablename = %s
            AND indexdef LIKE '%%vector%%'
        """, (table_name,))
        indexes = cur.fetchall()
        
        # Get table row count
        cur.execute(f"SELECT COUNT(*) AS count FROM {table_name} WHERE embedding IS NOT NULL")
        vector_count = cur.fetchone()['count']
        
        return {
            "indexes": indexes,
            "vector_count": vector_count
        }


def tune_search_params(conn, target_recall: float = 0.95):
    """
    Suggest search parameter tuning based on current settings.
    """
    suggestions = []
    
    with conn.cursor() as cur:
        # Check current HNSW ef_search
        cur.execute("SHOW hnsw.ef_search")
        ef_search = int(cur.fetchone()['hnsw.ef_search'])
        
        # Check current IVFFlat probes
        cur.execute("SHOW ivfflat.probes")
        probes = int(cur.fetchone()['ivfflat.probes'])
    
    if target_recall > 0.95:
        if ef_search < 100:
            suggestions.append(f"Increase hnsw.ef_search from {ef_search} to 100-200 for better recall")
        if probes < 10:
            suggestions.append(f"Increase ivfflat.probes from {probes} to 10-20 for better recall")
    
    return {
        "current_ef_search": ef_search,
        "current_probes": probes,
        "suggestions": suggestions
    }


def benchmark_search(conn, iterations: int = 100, limit: int = 10) -> Dict:
    """Benchmark vector search performance."""
    times = []
    
    for _ in range(iterations):
        query_vec = generate_random_vector()
        
        start = time.time()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, title, embedding <=> %s::vector AS distance
                FROM documents
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, (query_vec, query_vec, limit))
            cur.fetchall()
        
        times.append(time.time() - start)
    
    return {
        "iterations": iterations,
        "avg_ms": sum(times) / len(times) * 1000,
        "min_ms": min(times) * 1000,
        "max_ms": max(times) * 1000,
        "p50_ms": sorted(times)[len(times)//2] * 1000,
        "p99_ms": sorted(times)[int(len(times)*0.99)] * 1000
    }


def run_demo(conn):
    """Run demonstration of vector search capabilities."""
    print("\n=== pgvector Search Demo ===\n")
    
    # Check index stats
    print("1. Index Statistics:")
    stats = check_index_stats(conn)
    print(f"   Vectors in database: {stats['vector_count']}")
    for idx in stats['indexes']:
        print(f"   Index: {idx['indexname']} ({idx['size']})")
    
    if stats['vector_count'] == 0:
        print("\n   ⚠ No vectors found. Run create_search_tables.py --with-sample-data first")
        print("   Then insert documents with embeddings")
        return
    
    # Generate query vector
    print("\n2. Basic Similarity Search:")
    query_vec = generate_random_vector()
    print(f"   Query: random {len(query_vec)}-dim vector")
    
    results = similarity_search(conn, query_vec, limit=5)
    for i, r in enumerate(results, 1):
        print(f"   {i}. {r['title'][:50]}... (dist: {r['distance']:.4f})")
    
    # Check tuning
    print("\n3. Search Parameter Tuning:")
    tuning = tune_search_params(conn)
    print(f"   Current hnsw.ef_search: {tuning['current_ef_search']}")
    print(f"   Current ivfflat.probes: {tuning['current_probes']}")
    for suggestion in tuning['suggestions']:
        print(f"   → {suggestion}")
    
    # Benchmark
    print("\n4. Search Benchmark (50 iterations):")
    bench = benchmark_search(conn, iterations=50)
    print(f"   Avg: {bench['avg_ms']:.2f}ms")
    print(f"   P50: {bench['p50_ms']:.2f}ms")
    print(f"   P99: {bench['p99_ms']:.2f}ms")
    
    print("\n=== Demo Complete ===")


def main():
    parser = argparse.ArgumentParser(
        description="pgvector search helpers and examples"
    )
    parser.add_argument("--host", default="localhost", help="Database host")
    parser.add_argument("--port", type=int, default=5432, help="Database port")
    parser.add_argument("--dbname", default="postgres", help="Database name")
    parser.add_argument("--user", default="postgres", help="Database user")
    parser.add_argument("--password", default="", help="Database password")
    parser.add_argument("--demo", action="store_true", help="Run search demo")
    parser.add_argument("--benchmark", action="store_true", help="Run performance benchmark")
    parser.add_argument("--iterations", type=int, default=100, help="Benchmark iterations")
    args = parser.parse_args()

    print(f"Connecting to {args.host}:{args.port}/{args.dbname}...")
    
    try:
        conn = connect(args.host, args.port, args.dbname, args.user, args.password)
    except psycopg2.Error as e:
        print(f"Error: Could not connect: {e}")
        sys.exit(1)

    if args.demo:
        run_demo(conn)
    elif args.benchmark:
        print("\nRunning benchmark...")
        results = benchmark_search(conn, iterations=args.iterations)
        print(f"\nResults ({results['iterations']} iterations):")
        print(f"  Average: {results['avg_ms']:.2f}ms")
        print(f"  Min: {results['min_ms']:.2f}ms")
        print(f"  Max: {results['max_ms']:.2f}ms")
        print(f"  P50: {results['p50_ms']:.2f}ms")
        print(f"  P99: {results['p99_ms']:.2f}ms")
    else:
        print("\nUsage:")
        print("  --demo       Run interactive demo")
        print("  --benchmark  Run performance benchmark")
    
    conn.close()


if __name__ == "__main__":
    main()

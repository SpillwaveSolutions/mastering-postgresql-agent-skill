# Python Query Patterns Reference

Bulk inserts, full-text search (FTS), vector similarity queries, and JSONB/array operations.

## Contents

- [Bulk Insert Strategies](#bulk-insert-strategies)
- [Full-Text Search Queries](#full-text-search-queries)
- [Vector Similarity Queries](#vector-similarity-queries)
- [JSONB and Array Operations](#jsonb-and-array-operations)

---

## Bulk Insert Strategies

### Performance Comparison

| Method | Speed | Memory | Use Case |
|--------|-------|--------|----------|
| `executemany` | Slow | Low | Small batches |
| `execute_values` | Fast | Medium | Medium batches |
| `COPY` | Fastest | Higher | Large imports |
| `copy_records_to_table` | Fastest | Medium | asyncpg bulk |

### psycopg2: execute_values

```python
from psycopg2.extras import execute_values

data = [
    ("Title 1", "Content 1", [0.1, 0.2, 0.3]),
    ("Title 2", "Content 2", [0.4, 0.5, 0.6]),
    # ... thousands of rows
]

with conn.cursor() as cur:
    execute_values(
        cur,
        """INSERT INTO documents (title, content, embedding) 
           VALUES %s ON CONFLICT (id) DO NOTHING""",
        data,
        template="(%s, %s, %s::vector)",
        page_size=1000
    )
conn.commit()

# Verify insert count:
# cur.execute("SELECT COUNT(*) FROM documents")
# print(f"Inserted: {cur.fetchone()[0]} rows")
```

### psycopg2: COPY Protocol

```python
from io import StringIO
import csv

# Step 1: Prepare data as TSV
buffer = StringIO()
writer = csv.writer(buffer, delimiter='\t')
for row in data:
    writer.writerow(row)
buffer.seek(0)

# Step 2: Copy to table
with conn.cursor() as cur:
    cur.copy_from(buffer, 'documents', columns=('title', 'content'))
conn.commit()
```

### psycopg3: COPY with Binary

```python
async with conn.cursor() as cur:
    async with cur.copy("COPY documents (title, content) FROM STDIN (FORMAT BINARY)") as copy:
        for title, content in data:
            await copy.write_row((title, content))
```

### asyncpg: copy_records_to_table

```python
# Fastest method for asyncpg
records = [
    ("Title 1", "Content 1"),
    ("Title 2", "Content 2"),
]

await conn.copy_records_to_table(
    'documents',
    records=records,
    columns=['title', 'content']
)

# Verify:
# count = await conn.fetchval("SELECT COUNT(*) FROM documents")
```

### asyncpg: executemany (For Complex Queries)

```python
# Use when you need RETURNING or complex logic
await conn.executemany(
    """INSERT INTO documents (title, content) VALUES ($1, $2)
       ON CONFLICT (title) DO UPDATE SET content = EXCLUDED.content""",
    [("Title 1", "Content 1"), ("Title 2", "Content 2")]
)
```

---

## Full-Text Search Queries

### Basic FTS (All Libraries)

```python
# psycopg2/psycopg3 (uses %s placeholders)
cur.execute("""
    SELECT id, title, ts_rank(search_vector, query) AS rank,
           ts_headline('english', content, query) AS snippet
    FROM documents, websearch_to_tsquery('english', %s) query
    WHERE search_vector @@ query
    ORDER BY rank DESC
    LIMIT %s
""", (search_term, limit))

# asyncpg (uses $1, $2 placeholders)
rows = await conn.fetch("""
    SELECT id, title, ts_rank(search_vector, query) AS rank,
           ts_headline('english', content, query) AS snippet
    FROM documents, websearch_to_tsquery('english', $1) query
    WHERE search_vector @@ query
    ORDER BY rank DESC
    LIMIT $2
""", search_term, limit)
```

### FTS with Filters

```python
rows = await conn.fetch("""
    SELECT id, title, ts_rank(search_vector, query) AS rank
    FROM documents, websearch_to_tsquery('english', $1) query
    WHERE search_vector @@ query
      AND created_at > $2
      AND metadata @> $3::jsonb
    ORDER BY rank DESC
    LIMIT $4
""", search_term, since_date, json.dumps({"status": "published"}), limit)

# Verify index is used:
# EXPLAIN (ANALYZE) should show "Bitmap Index Scan"
```

### BM25 Search (pg_search)

```python
# ParadeDB only
rows = await conn.fetch("""
    SELECT id, title, paradedb.score(id) AS score,
           paradedb.snippet(content, $1) AS snippet
    FROM documents
    WHERE content @@@ $1
    ORDER BY paradedb.score(id) DESC
    LIMIT $2
""", search_term, limit)
```

---

## Vector Similarity Queries

### Step 1: Register pgvector Types

```python
# psycopg2
from pgvector.psycopg2 import register_vector
register_vector(conn)

# psycopg3
from pgvector.psycopg import register_vector
register_vector(conn)

# asyncpg
from pgvector.asyncpg import register_vector
await register_vector(conn)
```

### Step 2: Similarity Search

```python
import numpy as np

# Generate or load embedding
query_embedding = np.array([0.1, 0.2, ...])  # 1536 dims for OpenAI

# asyncpg query
rows = await conn.fetch("""
    SELECT id, title, embedding <=> $1 AS distance
    FROM documents
    ORDER BY embedding <=> $1
    LIMIT $2
""", query_embedding, limit)

# Convert distance to similarity (cosine distance is 0-2, lower is better)
results = [
    {"id": r["id"], "title": r["title"], "similarity": 1 - r["distance"]}
    for r in rows
]

# Verify index is used:
# EXPLAIN should show "Index Scan using idx_docs_embedding"
```

### Filtered Vector Search

```python
# Filter then search (efficient with partial index or pre-filtering)
rows = await conn.fetch("""
    SELECT id, title, embedding <=> $1 AS distance
    FROM documents
    WHERE category = $2
    ORDER BY embedding <=> $1
    LIMIT $3
""", embedding, category, limit)
```

### Hybrid Search Function

```python
async def hybrid_search(
    pool: asyncpg.Pool,
    query_text: str,
    query_embedding: list[float],
    text_weight: float = 0.3,
    vector_weight: float = 0.7,
    limit: int = 20
) -> list[dict]:
    """
    Combine FTS and vector search with weighted scoring.
    
    Args:
        pool: asyncpg connection pool
        query_text: Search keywords for FTS
        query_embedding: Vector for similarity search
        text_weight: Weight for text score (default 0.3)
        vector_weight: Weight for vector score (default 0.7)
        limit: Max results to return
    
    Returns:
        List of documents with combined_score
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH text_matches AS (
                SELECT id, ts_rank(search_vector, query) AS text_score
                FROM documents, websearch_to_tsquery('english', $1) query
                WHERE search_vector @@ query
            ),
            vector_matches AS (
                SELECT id, 1 - (embedding <=> $2::vector) AS vector_score
                FROM documents
                ORDER BY embedding <=> $2::vector
                LIMIT 100
            )
            SELECT d.id, d.title, d.content,
                   COALESCE(t.text_score, 0) * $3 + 
                   COALESCE(v.vector_score, 0) * $4 AS combined_score
            FROM documents d
            LEFT JOIN text_matches t ON d.id = t.id
            LEFT JOIN vector_matches v ON d.id = v.id
            WHERE t.id IS NOT NULL OR v.id IS NOT NULL
            ORDER BY combined_score DESC
            LIMIT $5
        """, query_text, query_embedding, text_weight, vector_weight, limit)
        
        return [dict(r) for r in rows]
```

### Reciprocal Rank Fusion (RRF)

RRF is the industry-standard algorithm for hybrid search. Unlike weighted scoring, RRF uses rank positions which normalizes across different score scales.

**Formula**: `score = 1 / (k + rank)` where k=60 is standard.

```python
async def hybrid_search_rrf(
    pool: asyncpg.Pool,
    query_text: str,
    query_embedding: list[float],
    k: int = 60,
    limit: int = 20
) -> list[dict]:
    """
    Hybrid search using Reciprocal Rank Fusion (RRF).

    RRF normalizes scores by rank position, making it more robust
    than weighted scoring when combining different search methods.

    Args:
        pool: asyncpg connection pool
        query_text: Keywords for full-text search
        query_embedding: Vector for semantic search
        k: RRF constant (default 60, industry standard)
        limit: Max results to return
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH semantic AS (
                SELECT id, RANK() OVER (ORDER BY embedding <=> $1::vector) as rank
                FROM documents
                ORDER BY embedding <=> $1::vector
                LIMIT 50
            ),
            keyword AS (
                SELECT id, RANK() OVER (
                    ORDER BY ts_rank_cd(search_vector, query) DESC
                ) as rank
                FROM documents, plainto_tsquery('english', $2) query
                WHERE search_vector @@ query
                LIMIT 50
            )
            SELECT
                COALESCE(s.id, k.id) as id,
                d.title,
                d.content,
                (COALESCE(1.0 / ($3 + s.rank), 0.0) +
                 COALESCE(1.0 / ($3 + k.rank), 0.0)) as rrf_score
            FROM semantic s
            FULL OUTER JOIN keyword k ON s.id = k.id
            JOIN documents d ON d.id = COALESCE(s.id, k.id)
            ORDER BY rrf_score DESC
            LIMIT $4
        """, query_embedding, query_text, k, limit)

        return [dict(r) for r in rows]
```

**When to use RRF vs Weighted:**
| Scenario | Recommendation |
|----------|----------------|
| Production hybrid search | RRF (more robust) |
| Known score distributions | Weighted (tunable) |
| Combining 3+ search methods | RRF (scales better) |

---

## JSONB and Array Operations

### JSONB Queries

```python
import json

# Containment query (uses GIN index)
rows = await conn.fetch("""
    SELECT * FROM products
    WHERE data @> $1::jsonb
""", json.dumps({"category": "electronics", "in_stock": True}))

# Extract and filter
rows = await conn.fetch("""
    SELECT id, data->>'name' AS name, (data->>'price')::numeric AS price
    FROM products
    WHERE (data->>'price')::numeric < $1
      AND data ? 'name'
    ORDER BY price
""", max_price)

# Update JSONB field
await conn.execute("""
    UPDATE products
    SET data = jsonb_set(data, '{status}', $1::jsonb)
    WHERE id = $2
""", json.dumps("active"), product_id)

# Verify update:
# row = await conn.fetchrow("SELECT data->>'status' FROM products WHERE id = $1", product_id)
# assert row[0] == "active"
```

### Array Queries

```python
# Find by tag overlap (posts with ANY of these tags)
rows = await conn.fetch("""
    SELECT * FROM posts
    WHERE tags && $1::text[]
""", ['python', 'postgresql'])

# Find by tag containment (posts with ALL of these tags)
rows = await conn.fetch("""
    SELECT * FROM posts
    WHERE tags @> $1::text[]
""", ['python', 'postgresql'])

# Add tag to array (avoid duplicates)
await conn.execute("""
    UPDATE posts
    SET tags = array_append(tags, $1)
    WHERE id = $2 AND NOT ($1 = ANY(tags))
""", 'new-tag', post_id)

# Remove tag from array
await conn.execute("""
    UPDATE posts
    SET tags = array_remove(tags, $1)
    WHERE id = $2
""", 'old-tag', post_id)
```

---

## Related References

- [python-drivers.md](python-drivers.md) — Driver selection, connection patterns, pools, SQLAlchemy

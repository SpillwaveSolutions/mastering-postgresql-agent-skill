# Vectors, JSONB & Index Management Reference

pgvector similarity search, JSONB/array indexing strategies, and index maintenance.

## Contents

- [pgvector Deep Dive](#pgvector-deep-dive)
- [JSONB Indexing](#jsonb-indexing)
- [Array Indexing](#array-indexing)
- [Index Type Selection](#index-type-selection)
- [Index Maintenance](#index-maintenance)
- [Troubleshooting](#troubleshooting)

---

## pgvector Deep Dive

### Vector Column Creation

```sql
-- Fixed dimensions
CREATE TABLE items (
    id BIGSERIAL PRIMARY KEY,
    embedding vector(1536)  -- OpenAI ada-002
);

-- Verify dimensions
SELECT vector_dims(embedding) FROM items LIMIT 1;
```

### Distance Operators

| Operator | Function | Index Ops | Use Case |
|----------|----------|-----------|----------|
| `<->` | L2 (Euclidean) | `vector_l2_ops` | General |
| `<=>` | Cosine | `vector_cosine_ops` | Normalized embeddings |
| `<#>` | Neg inner product | `vector_ip_ops` | Max inner product |
| `<+>` | L1 (Manhattan) | `vector_l1_ops` | Sparse vectors |

```sql
-- Cosine similarity (most common)
SELECT id, title, embedding <=> $1::vector AS distance
FROM documents
ORDER BY embedding <=> $1::vector
LIMIT 10;

-- Convert distance to similarity
SELECT id, title, 1 - (embedding <=> $1::vector) AS similarity
FROM documents
ORDER BY embedding <=> $1::vector
LIMIT 10;

-- Verify pgvector is working
SELECT '[1,2,3]'::vector <=> '[4,5,6]'::vector AS test_distance;
-- Expected: ~5.196 (Euclidean distance)
```

### HNSW Index

Hierarchical Navigable Small World - best for query performance.

```sql
CREATE INDEX ON documents USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Verify index created
SELECT indexname, indexdef FROM pg_indexes 
WHERE indexdef LIKE '%hnsw%';
```

| Parameter | Default | Range | Effect |
|-----------|---------|-------|--------|
| `m` | 16 | 4-64 | Connections per node. Higher = better recall, more memory |
| `ef_construction` | 64 | 32-512 | Build quality. Higher = better index, slower build |

**Query-time tuning:**

```sql
SET hnsw.ef_search = 100;  -- Default 40. Higher = better recall, slower

-- Verify setting
SHOW hnsw.ef_search;
```

**Filtered query optimization (pgvector 0.7+):**

```sql
-- Enable iterative scan for filtered queries
SET hnsw.iterative_scan = strict_order;  -- or 'relaxed_order' for better recall
SET hnsw.max_scan_tuples = 50000;        -- Limit tuples scanned
SET hnsw.scan_mem_multiplier = 2;        -- Memory multiplier for scans (default: 1)

-- Query with filter uses iterative scan
SELECT * FROM documents
WHERE category = 'tutorial'
ORDER BY embedding <=> $1::vector
LIMIT 10;
```

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `hnsw.iterative_scan` | off | Enable iterative scanning for filtered queries |
| `hnsw.max_scan_tuples` | 20000 | Max tuples to visit during iterative scan |
| `hnsw.scan_mem_multiplier` | 1 | Memory usage relative to `work_mem` |

| Mode | Behavior |
|------|----------|
| `strict_order` | Maintains exact distance ordering |
| `relaxed_order` | Better recall, may reorder slightly |

**Build memory:**

```sql
SET maintenance_work_mem = '2GB';  -- More = faster build
SET max_parallel_maintenance_workers = 7;  -- Parallel build

-- Monitor build progress
SELECT * FROM pg_stat_progress_create_index;
```

### IVFFlat Index

Inverted File with Flat compression - faster build, requires data.

```sql
-- Must have data before creating index
CREATE INDEX ON documents USING ivfflat (embedding vector_l2_ops)
WITH (lists = 100);
```

| Dataset Size | lists Value |
|--------------|-------------|
| < 1M rows | `sqrt(rows)` |
| > 1M rows | `rows / 1000` |

**Query-time tuning:**

```sql
SET ivfflat.probes = 10;  -- Default 1. Higher = better recall
```

### Index Selection Guide

| Factor | HNSW | IVFFlat |
|--------|------|---------|
| Query speed | ✅ ~15x faster | Slower |
| Build time | Slower | ✅ Faster |
| Index size | Larger (~2.8x) | ✅ Smaller |
| Empty table | ✅ Works | ❌ Needs data |
| Updates | ✅ Handles well | May degrade |
| Recall at same speed | ✅ Better | Lower |

**Recommendation:** Use HNSW unless build time is critical.

### VectorChord (Large-Scale Alternative)

For datasets exceeding 100M vectors, VectorChord offers significant performance improvements over pgvector while maintaining API compatibility.

```sql
-- Install VectorChord (self-hosted only)
CREATE EXTENSION vchord CASCADE;

-- Create vchordrq index (IVF + RaBitQ quantization)
CREATE INDEX ON documents
USING vchordrq (embedding vector_l2_ops)
WITH (options = $$
    residual_quantization = true
    [build.internal]
    lists = [4096]
$$);

-- Query uses same syntax as pgvector
SELECT id, title, embedding <-> $1::vector AS distance
FROM documents
ORDER BY embedding <-> $1::vector
LIMIT 10;
```

| Factor | pgvector HNSW | VectorChord vchordrq |
|--------|---------------|----------------------|
| Query speed | Fast | 5x faster |
| Insert throughput | Good | 16x higher |
| Index build | Slower | 16x faster |
| Scale | Millions | Billions (3B+ in production) |
| Memory (100M vectors) | ~50GB+ | ~32GB |
| Cloud managed | ✅ All major | ❌ Self-host only |
| pgvector compatible | N/A | ✅ Full API compatibility |

**When to consider VectorChord:**
- Datasets > 100M vectors
- Cost-sensitive deployments (400K vectors per $1 vs 15K for pgvector)
- Self-hosted infrastructure acceptable

> **Note:** Added to Thoughtworks Technology Radar (April 2025) as "Assess" category.

### Dimension Limits

| Type | Max Indexed Dims | Use Case |
|------|------------------|----------|
| `vector` | 2,000 | Standard embeddings |
| `halfvec` | 4,000 | Large models, half precision |
| `bit` | 64,000 | Binary quantization |
| `sparsevec` | 1,000 non-zero | Sparse embeddings |

### Hybrid Search Pattern

```sql
-- Combine keyword + vector search
WITH keyword_matches AS (
    SELECT id, ts_rank(search_vector, query) AS text_rank
    FROM documents, websearch_to_tsquery('english', $1) query
    WHERE search_vector @@ query
),
vector_matches AS (
    SELECT id, 1 - (embedding <=> $2::vector) AS vector_score
    FROM documents
    ORDER BY embedding <=> $2::vector
    LIMIT 100
)
SELECT d.id, d.title,
       COALESCE(k.text_rank, 0) * 0.3 + COALESCE(v.vector_score, 0) * 0.7 AS combined_score
FROM documents d
LEFT JOIN keyword_matches k ON d.id = k.id
LEFT JOIN vector_matches v ON d.id = v.id
WHERE k.id IS NOT NULL OR v.id IS NOT NULL
ORDER BY combined_score DESC
LIMIT 20;
```

---

## JSONB Indexing

### Index Types for JSONB

| Index | Operators | Size | Use Case |
|-------|-----------|------|----------|
| GIN default | `?`, `?|`, `?&`, `@>`, `<@` | Larger | General queries |
| GIN jsonb_path_ops | `@>` only | Smaller | Containment only |
| B-tree expression | `=`, `<`, `>` | Smallest | Specific field |

### GIN Index (Default)

```sql
CREATE INDEX idx_data ON products USING GIN (data);

-- Supports these queries:
SELECT * FROM products WHERE data ? 'price';           -- Key exists
SELECT * FROM products WHERE data ?| array['a','b'];   -- Any key exists
SELECT * FROM products WHERE data ?& array['a','b'];   -- All keys exist
SELECT * FROM products WHERE data @> '{"status":"active"}';  -- Contains

-- Verify index is used
EXPLAIN SELECT * FROM products WHERE data @> '{"status":"active"}';
-- Should show: Bitmap Index Scan on idx_data
```

### GIN jsonb_path_ops

```sql
CREATE INDEX idx_data_path ON products USING GIN (data jsonb_path_ops);

-- Only supports containment:
SELECT * FROM products WHERE data @> '{"category":"electronics"}';
```

### Expression Index

```sql
-- Index specific field for equality/range queries
CREATE INDEX idx_price ON products ((data->>'price')::numeric);

-- Query uses index
SELECT * FROM products WHERE (data->>'price')::numeric < 100;

-- Index nested path
CREATE INDEX idx_category ON products ((data#>>'{metadata,category}'));
```

### JSONB Query Patterns

```sql
-- Access operators
data->'key'          -- Returns JSON
data->>'key'         -- Returns text
data#>'{a,b}'        -- Path access, returns JSON
data#>>'{a,b}'       -- Path access, returns text

-- Array element access
data->0              -- First array element
data->>-1            -- Last array element (text)

-- Containment (index-friendly)
data @> '{"a":1}'    -- data contains {"a":1}
data <@ '{"a":1}'    -- data is contained by {"a":1}
```

---

## Array Indexing

### GIN Index for Arrays

```sql
CREATE INDEX idx_tags ON posts USING GIN (tags);

-- Verify
SELECT indexname FROM pg_indexes WHERE indexname = 'idx_tags';
```

### intarray Extension (Integer Arrays)

For integer arrays, the `intarray` extension provides an optimized operator class:

```sql
-- Enable extension
CREATE EXTENSION intarray;

-- Create optimized index for integer arrays
CREATE INDEX idx_labels ON items USING GIN (label_ids gin__int_ops);

-- Queries use same operators but with better performance
SELECT * FROM items WHERE label_ids @> ARRAY[1, 5, 10];
SELECT * FROM items WHERE label_ids && ARRAY[1, 2, 3];
```

| Index Type | Best For | Size | Performance |
|------------|----------|------|-------------|
| GIN (default) | Text/any arrays | Larger | Good |
| GIN gin__int_ops | Integer arrays | Smaller | Better |

### Array Operators (Index-Supported)

| Operator | Meaning | Example |
|----------|---------|---------|
| `@>` | Contains | `tags @> ARRAY['a','b']` |
| `<@` | Contained by | `tags <@ ARRAY['a','b','c']` |
| `&&` | Overlaps (any) | `tags && ARRAY['a','b']` |
| `=` | Equals | `tags = ARRAY['a','b']` |

```sql
-- Find posts with all these tags
SELECT * FROM posts WHERE tags @> ARRAY['python', 'postgresql'];

-- Find posts with any of these tags
SELECT * FROM posts WHERE tags && ARRAY['python', 'go', 'rust'];

-- Check specific element (not index-optimized)
SELECT * FROM posts WHERE 'python' = ANY(tags);
```

---

## Index Type Selection

### Decision Matrix

| Column Type | Query Pattern | Recommended Index |
|-------------|---------------|-------------------|
| Scalar | `=`, `<`, `>` | B-tree (default) |
| Scalar | `LIKE 'prefix%'` | B-tree |
| Scalar | `LIKE '%substr%'` | GIN + pg_trgm |
| tsvector | `@@` | GIN |
| vector | `<->`, `<=>` | HNSW or IVFFlat |
| JSONB | `@>`, `?` | GIN |
| JSONB | `@>` only | GIN jsonb_path_ops |
| JSONB | Specific field `=` | B-tree expression |
| Array | `@>`, `&&` | GIN |
| Timestamp (ordered) | Range scans | BRIN |
| Geometric | `&&`, `@>` | GiST |

### Partial Indexes

```sql
-- Index only active records
CREATE INDEX idx_active_orders ON orders (created_at)
WHERE status = 'active';

-- Query must include the WHERE clause
SELECT * FROM orders WHERE status = 'active' AND created_at > '2024-01-01';
```

### Covering Indexes

```sql
-- Include columns to enable index-only scans
CREATE INDEX idx_users_email ON users (email) INCLUDE (name, created_at);

-- This query can be satisfied from index alone
SELECT email, name, created_at FROM users WHERE email = 'test@example.com';

-- Verify index-only scan
EXPLAIN SELECT email, name, created_at FROM users WHERE email = 'test@example.com';
-- Should show: Index Only Scan
```

---

## Index Maintenance

### Autovacuum Settings for Vector Tables

HNSW and GIN indexes generate significant bloat during updates. Configure aggressive autovacuum for vector-heavy tables:

```sql
-- Aggressive settings for vector tables
ALTER TABLE documents SET (
    autovacuum_vacuum_scale_factor = 0.01,   -- Trigger at 1% changed (default 20%)
    autovacuum_vacuum_threshold = 50,         -- Minimum rows before trigger
    autovacuum_analyze_scale_factor = 0.01,   -- Keep statistics fresh
    autovacuum_vacuum_cost_delay = 2          -- Faster vacuum execution
);

-- Verify settings
SELECT relname, reloptions
FROM pg_class
WHERE relname = 'documents';
```

**Why aggressive settings for vectors:**
- HNSW graph structure creates many dead tuples on updates
- Bloated indexes degrade query performance significantly
- Default 20% threshold is too high for vector workloads

### Monitor Index Usage

```sql
-- Unused indexes (candidates for removal)
SELECT schemaname, relname, indexrelname, idx_scan,
       pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
AND indexrelname NOT LIKE '%pkey%'
ORDER BY pg_relation_size(indexrelid) DESC;

-- Index hit ratio (should be > 0.99)
SELECT relname,
       round(100.0 * idx_scan / nullif(seq_scan + idx_scan, 0), 2) AS idx_ratio,
       seq_scan, idx_scan
FROM pg_stat_user_tables
WHERE n_live_tup > 10000
ORDER BY idx_ratio ASC;
```

### Reindex Operations

```sql
-- Rebuild specific index (locks table)
REINDEX INDEX idx_documents_search;

-- Concurrent rebuild (no lock, slower)
REINDEX INDEX CONCURRENTLY idx_documents_search;

-- Rebuild all indexes on table
REINDEX TABLE documents;

-- Verify reindex completed
SELECT indexname, pg_size_pretty(pg_relation_size(indexname::regclass)) 
FROM pg_indexes WHERE tablename = 'documents';
```

### Index Bloat Detection

```sql
-- Estimate bloat ratio
SELECT nspname, relname,
       round(100 * pg_relation_size(indexrelid) / 
             nullif(pg_relation_size(indrelid), 0)) AS index_ratio
FROM pg_index
JOIN pg_class ON pg_class.oid = pg_index.indexrelid
JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
WHERE nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_relation_size(indexrelid) DESC;
```

---

## Troubleshooting

### Index Not Used

```sql
-- Check query plan
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM documents WHERE ...;

-- If Seq Scan appears:
-- 1. Update statistics
ANALYZE documents;

-- 2. Verify index exists
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'documents';

-- 3. Check operator class matches query
-- vector_cosine_ops for <=>, vector_l2_ops for <->
```

### Poor Full-Text Results

```sql
-- Check what tokens are generated
SELECT to_tsvector('english', 'your document text');

-- Verify query parsing
SELECT websearch_to_tsquery('english', 'your search query');

-- Check if they match
SELECT to_tsvector('english', 'text') @@ to_tsquery('english', 'query');
```

### Vector Search Quality Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Low recall | Low ef_search/probes | Increase query-time parameter |
| Wrong results | Mismatched distance | Check operator matches index ops |
| Slow queries | No index | Create HNSW index |
| OOM on build | Low maintenance_work_mem | Increase to 2GB+ |

### Common Error Messages

| Error | Cause | Fix |
|-------|-------|-----|
| `operator does not exist: vector <=> vector` | No extension | `CREATE EXTENSION vector;` |
| `index row size exceeds maximum` | Dimensions > 2000 | Use halfvec or reduce dims |
| `could not determine which collation to use` | Missing language | Specify config: `'english'` |

---

## Related References

- [search-fulltext.md](search-fulltext.md) — Full-text search, BM25, trigram fuzzy search

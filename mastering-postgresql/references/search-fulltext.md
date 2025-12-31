# Full-Text Search Reference

Native PostgreSQL full-text search, BM25 ranking with pg_search, and trigram fuzzy matching.

## Contents

- [Native Full-Text Search](#native-full-text-search)
- [BM25 with pg_search](#bm25-with-pg_search)
- [Trigram Fuzzy Search](#trigram-fuzzy-search)

---

## Native Full-Text Search

### Core Concepts

| Type | Purpose | Example |
|------|---------|---------|
| `tsvector` | Normalized document | `'cat':1 'dog':2` |
| `tsquery` | Search query | `'cat' & 'dog'` |
| `@@` | Match operator | `tsvector @@ tsquery` |

### Creating tsvector Columns

```sql
-- Option 1: Generated column (recommended)
ALTER TABLE documents ADD COLUMN search_vector tsvector
GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(content, '')), 'B')
) STORED;

-- Verify it works:
SELECT search_vector FROM documents LIMIT 1;
-- Expected: tsvector with weighted terms

-- Option 2: Trigger-maintained (for complex logic)
CREATE OR REPLACE FUNCTION documents_search_trigger() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.content, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tsvector_update BEFORE INSERT OR UPDATE
ON documents FOR EACH ROW EXECUTE FUNCTION documents_search_trigger();
```

### Query Functions

| Function | Input | Use Case |
|----------|-------|----------|
| `to_tsquery` | `'fat & (rat | cat)'` | Full control, boolean |
| `plainto_tsquery` | `'fat rat'` | Simple AND of words |
| `phraseto_tsquery` | `'fat rat'` | Adjacent words |
| `websearch_to_tsquery` | `'"fat rat" -cat'` | User-facing search |

```sql
-- websearch_to_tsquery supports:
-- "quoted phrases", -negation, OR operator
SELECT * FROM documents
WHERE search_vector @@ websearch_to_tsquery('english', '"database index" -mysql');
```

### Ranking Functions

```sql
-- ts_rank: term frequency based
SELECT title, ts_rank(search_vector, query) AS rank
FROM documents, to_tsquery('english', 'postgresql') query
WHERE search_vector @@ query
ORDER BY rank DESC;

-- ts_rank_cd: cover density (phrase proximity)
SELECT title, ts_rank_cd(search_vector, query) AS rank
FROM documents, phraseto_tsquery('english', 'full text search') query
WHERE search_vector @@ query
ORDER BY rank DESC;

-- Normalization options (bitmask)
-- 1: divides by 1 + log(document length)
-- 2: divides by document length
-- 4: divides by mean harmonic distance between extents
SELECT ts_rank(search_vector, query, 1) AS normalized_rank
FROM documents, to_tsquery('english', 'search') query;
```

### Highlighting Results

```sql
SELECT title,
       ts_headline('english', content, query,
           'StartSel=<b>, StopSel=</b>, MaxWords=35, MinWords=15'
       ) AS snippet
FROM documents, websearch_to_tsquery('english', 'postgresql search') query
WHERE search_vector @@ query;
```

### Weight Configuration

| Weight | Default Rank | Typical Use |
|--------|--------------|-------------|
| A | 1.0 | Title, name |
| B | 0.4 | Abstract, summary |
| C | 0.2 | Body content |
| D | 0.1 | Metadata, tags |

```sql
-- Custom weight array [D, C, B, A]
SELECT ts_rank('{0.1, 0.2, 0.4, 1.0}', search_vector, query) AS rank
FROM documents, to_tsquery('postgresql') query;
```

### Full-Text Search Verification

```sql
-- Verify index exists and is used
EXPLAIN (ANALYZE) SELECT * FROM documents 
WHERE search_vector @@ to_tsquery('postgresql');
-- Should show: Index Scan using idx_documents_search

-- Debug tokenization
SELECT to_tsvector('english', 'PostgreSQL full-text searching');
-- Output: 'full':2 'full-text':2 'postgresql':1 'search':3 'text':3
```

---

## BM25 with pg_search

BM25 (Best Match 25) provides relevance scoring that considers term frequency and inverse document frequency. Available via pg_search extension in ParadeDB.

### Installation

```sql
-- ParadeDB image only
CREATE EXTENSION pg_search;

-- Verify installation
SELECT extname, extversion FROM pg_extension WHERE extname = 'pg_search';
-- Expected: pg_search with version number
```

### Creating BM25 Index

```sql
-- Basic index
CREATE INDEX idx_products_search ON products
USING bm25 (id, title, description, category)
WITH (key_field='id');

-- With custom tokenizer
CREATE INDEX idx_docs_search ON documents
USING bm25 (id, title, content)
WITH (
    key_field='id',
    text_fields='{"title": {"tokenizer": "en_stem"}, "content": {"tokenizer": "en_stem"}}'
);

-- Verify index created
SELECT indexname FROM pg_indexes WHERE indexname LIKE '%bm25%';
```

### BM25 Queries

```sql
-- Basic search with @@@ operator
SELECT title, description, paradedb.score(id) AS score
FROM products
WHERE description @@@ 'wireless keyboard'
ORDER BY paradedb.score(id) DESC;

-- Phrase search
SELECT * FROM products
WHERE description @@@ '"mechanical keyboard"';

-- Boolean operators
SELECT * FROM products
WHERE description @@@ 'wireless AND (keyboard OR mouse)';

-- Fuzzy matching
SELECT * FROM products
WHERE id @@@ paradedb.match('title', 'keybord', distance => 1);

-- Field boosting
SELECT * FROM products
WHERE id @@@ paradedb.boost(
    paradedb.match('title', 'keyboard'),
    2.0
);
```

### Highlighting with BM25

```sql
SELECT title,
       paradedb.snippet(description, 'wireless keyboard') AS snippet
FROM products
WHERE description @@@ 'wireless keyboard';
```

### BM25 vs ts_rank Comparison

| Feature | ts_rank | BM25 (pg_search) |
|---------|---------|------------------|
| IDF weighting | ❌ | ✅ |
| Document length normalization | Basic | ✅ Configurable |
| Query speed | Fast | ~20x faster ranking |
| Fuzzy matching | Via pg_trgm | Built-in |
| Phrase search | Via <-> | Built-in quotes |
| Setup complexity | Low | Medium |

### Alternative: pg_textsearch (TigerData)

> **Note**: pg_textsearch is in preview status as of December 2025.

TigerData's pg_textsearch provides BM25 ranking optimized for hybrid AI search workflows.

```sql
-- TigerData/Timescale pg_textsearch (preview)
CREATE EXTENSION pg_textsearch;

-- Create BM25 index
CREATE INDEX ON products USING bm25 (title, description);

-- Query with <@> operator
SELECT title, bm25_score(products) AS score
FROM products
WHERE description <@> 'wireless keyboard'
ORDER BY score DESC;
```

| Feature | pg_search (ParadeDB) | pg_textsearch (TigerData) |
|---------|---------------------|---------------------------|
| Status | Production | Preview |
| Operator | `@@@` | `<@>` |
| Engine | Tantivy (Rust) | Custom |
| Focus | Full search platform | BM25 for hybrid AI |

---

## Trigram Fuzzy Search

pg_trgm enables similarity-based matching for typo tolerance.

### Setup

```sql
CREATE EXTENSION pg_trgm;

-- Verify installation
SHOW pg_trgm.similarity_threshold;
-- Default: 0.3

-- Index for similarity queries
CREATE INDEX idx_products_name_trgm ON products USING GIN (name gin_trgm_ops);

-- Index for LIKE/ILIKE optimization
CREATE INDEX idx_products_desc_trgm ON products USING GIN (description gin_trgm_ops);
```

### Similarity Functions

```sql
-- similarity(): 0-1 score
SELECT name, similarity(name, 'Postgre') AS sim
FROM products
WHERE similarity(name, 'Postgre') > 0.3
ORDER BY sim DESC;

-- % operator: uses pg_trgm.similarity_threshold
SET pg_trgm.similarity_threshold = 0.4;
SELECT * FROM products WHERE name % 'Postgre';

-- word_similarity(): best matching substring
SELECT name, word_similarity('SQL', name) AS sim
FROM products
WHERE 'SQL' <% name;  -- word similarity threshold
```

### LIKE/ILIKE Optimization

```sql
-- GIN index on gin_trgm_ops accelerates wildcard queries
SELECT * FROM products WHERE name ILIKE '%keyboard%';
SELECT * FROM products WHERE name LIKE '%key%board%';

-- Verify index is used
EXPLAIN SELECT * FROM products WHERE name ILIKE '%keyboard%';
-- Should show: Bitmap Index Scan on idx_products_name_trgm
```

---

## Related References

- [search-vectors-json.md](search-vectors-json.md) — pgvector, JSONB indexing, array indexing, maintenance

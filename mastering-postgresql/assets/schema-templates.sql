-- PostgreSQL Schema Templates for Search and Vector Workloads
-- Copy and modify these templates for your application

--------------------------------------------------------------------------------
-- EXTENSIONS (run first)
--------------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;           -- pgvector for embeddings
CREATE EXTENSION IF NOT EXISTS pg_trgm;          -- Trigram for fuzzy search
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";      -- UUID generation
-- CREATE EXTENSION IF NOT EXISTS pg_search;     -- BM25 (ParadeDB only)
-- CREATE EXTENSION IF NOT EXISTS pg_stat_statements; -- Query monitoring

--------------------------------------------------------------------------------
-- TEMPLATE 1: Documents with Full-Text and Vector Search
--------------------------------------------------------------------------------
CREATE TABLE documents (
    id BIGSERIAL PRIMARY KEY,
    
    -- Core content
    title TEXT NOT NULL,
    content TEXT,
    
    -- Flexible metadata
    metadata JSONB DEFAULT '{}',
    tags TEXT[] DEFAULT '{}',
    
    -- Vector embedding (adjust dimensions for your model)
    -- OpenAI ada-002: 1536, text-embedding-3-small: 1536, text-embedding-3-large: 3072
    embedding vector(1536),
    
    -- Generated full-text search vector
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(content, '')), 'B')
    ) STORED,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for documents
CREATE INDEX idx_docs_search ON documents USING GIN (search_vector);
CREATE INDEX idx_docs_embedding ON documents USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_docs_metadata ON documents USING GIN (metadata jsonb_path_ops);
CREATE INDEX idx_docs_tags ON documents USING GIN (tags);
CREATE INDEX idx_docs_created ON documents (created_at DESC);
CREATE INDEX idx_docs_title_trgm ON documents USING GIN (title gin_trgm_ops);

--------------------------------------------------------------------------------
-- TEMPLATE 2: Products with BM25 Search (ParadeDB)
--------------------------------------------------------------------------------
CREATE TABLE products (
    id BIGSERIAL PRIMARY KEY,
    
    -- Product info
    name TEXT NOT NULL,
    description TEXT,
    category TEXT,
    price NUMERIC(10, 2),
    
    -- Structured data
    attributes JSONB DEFAULT '{}',
    tags TEXT[] DEFAULT '{}',
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Standard indexes
CREATE INDEX idx_products_category ON products (category);
CREATE INDEX idx_products_price ON products (price);
CREATE INDEX idx_products_attributes ON products USING GIN (attributes jsonb_path_ops);
CREATE INDEX idx_products_tags ON products USING GIN (tags);
CREATE INDEX idx_products_name_trgm ON products USING GIN (name gin_trgm_ops);

-- BM25 index (ParadeDB only)
-- CREATE INDEX idx_products_bm25 ON products 
--     USING bm25 (id, name, description, category) 
--     WITH (key_field='id');

--------------------------------------------------------------------------------
-- TEMPLATE 3: RAG Knowledge Base
--------------------------------------------------------------------------------
CREATE TABLE knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Source document reference
    source_id UUID NOT NULL,
    source_type TEXT NOT NULL,  -- 'pdf', 'webpage', 'document', etc.
    source_url TEXT,
    
    -- Chunk content
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    
    -- Vector embedding
    embedding vector(1536),
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for RAG queries
CREATE INDEX idx_chunks_source ON knowledge_chunks (source_id);
CREATE INDEX idx_chunks_embedding ON knowledge_chunks 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_chunks_metadata ON knowledge_chunks USING GIN (metadata);

-- Partial index for specific source types
CREATE INDEX idx_chunks_pdf ON knowledge_chunks (source_id, chunk_index)
    WHERE source_type = 'pdf';

--------------------------------------------------------------------------------
-- TEMPLATE 4: User Activity with Time-Series Optimization
--------------------------------------------------------------------------------
CREATE TABLE user_activity (
    id BIGSERIAL,
    user_id UUID NOT NULL,
    activity_type TEXT NOT NULL,
    activity_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    
    -- Partition by month for time-series queries
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Create monthly partitions
CREATE TABLE user_activity_2024_01 PARTITION OF user_activity
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
CREATE TABLE user_activity_2024_02 PARTITION OF user_activity
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');
-- Continue for other months...

-- BRIN index for time-range queries (very efficient for time-series)
CREATE INDEX idx_activity_time ON user_activity USING BRIN (created_at);
CREATE INDEX idx_activity_user ON user_activity (user_id, created_at DESC);

--------------------------------------------------------------------------------
-- HELPER: Updated Timestamp Trigger
--------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to tables
CREATE TRIGGER documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

--------------------------------------------------------------------------------
-- HELPER: Full-Text Search Configuration (custom dictionary)
--------------------------------------------------------------------------------
-- Example: Create a custom search config with synonym support
-- CREATE TEXT SEARCH DICTIONARY english_syn (
--     TEMPLATE = synonym,
--     SYNONYMS = my_synonyms  -- requires synonyms file
-- );
-- 
-- CREATE TEXT SEARCH CONFIGURATION english_custom (COPY = english);
-- ALTER TEXT SEARCH CONFIGURATION english_custom
--     ALTER MAPPING FOR asciiword WITH english_syn, english_stem;

--------------------------------------------------------------------------------
-- SAMPLE QUERIES
--------------------------------------------------------------------------------
-- Full-text search with ranking
-- SELECT id, title, ts_rank(search_vector, query) AS rank
-- FROM documents, websearch_to_tsquery('english', 'search terms') query
-- WHERE search_vector @@ query
-- ORDER BY rank DESC LIMIT 20;

-- Vector similarity search
-- SELECT id, title, embedding <=> '[0.1, 0.2, ...]'::vector AS distance
-- FROM documents
-- ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector
-- LIMIT 10;

-- Hybrid search (combine text + vector)
-- WITH text_results AS (
--     SELECT id, ts_rank(search_vector, query) AS score
--     FROM documents, websearch_to_tsquery('english', 'search') query
--     WHERE search_vector @@ query
-- ),
-- vector_results AS (
--     SELECT id, 1 - (embedding <=> $1::vector) AS score
--     FROM documents
--     ORDER BY embedding <=> $1::vector LIMIT 50
-- )
-- SELECT d.*, COALESCE(t.score, 0) * 0.3 + COALESCE(v.score, 0) * 0.7 AS combined
-- FROM documents d
-- LEFT JOIN text_results t ON d.id = t.id
-- LEFT JOIN vector_results v ON d.id = v.id
-- WHERE t.id IS NOT NULL OR v.id IS NOT NULL
-- ORDER BY combined DESC;

-- JSONB containment query
-- SELECT * FROM products WHERE attributes @> '{"color": "blue"}';

-- Array overlap query
-- SELECT * FROM documents WHERE tags && ARRAY['python', 'postgresql'];

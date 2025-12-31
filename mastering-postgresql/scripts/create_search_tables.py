#!/usr/bin/env python3
"""
Script: create_search_tables.py
Purpose: Create search-ready tables with full-text search and vector columns
Usage: python create_search_tables.py --host localhost --dbname mydb --user postgres

Creates a documents table with:
- Full-text search via generated tsvector column
- Vector similarity via pgvector column
- JSONB metadata field
- Array tags field
- Appropriate indexes for all search types
"""

import argparse
import sys

try:
    import psycopg2
except ImportError:
    print("Error: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


SCHEMA_SQL = """
-- Documents table with full-text and vector search support
CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT,
    metadata JSONB DEFAULT '{}',
    tags TEXT[] DEFAULT '{}',
    embedding vector(1536),  -- OpenAI ada-002 dimensions
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(content, '')), 'B')
    ) STORED,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Full-text search index (GIN)
CREATE INDEX IF NOT EXISTS idx_documents_search 
ON documents USING GIN (search_vector);

-- Vector similarity index (HNSW for cosine distance)
CREATE INDEX IF NOT EXISTS idx_documents_embedding 
ON documents USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- JSONB containment index
CREATE INDEX IF NOT EXISTS idx_documents_metadata 
ON documents USING GIN (metadata jsonb_path_ops);

-- Array overlap index
CREATE INDEX IF NOT EXISTS idx_documents_tags 
ON documents USING GIN (tags);

-- Timestamp index for sorting
CREATE INDEX IF NOT EXISTS idx_documents_created 
ON documents (created_at DESC);

-- Trigram index for fuzzy title search (requires pg_trgm)
CREATE INDEX IF NOT EXISTS idx_documents_title_trgm 
ON documents USING GIN (title gin_trgm_ops);

-- Updated timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS documents_updated_at ON documents;
CREATE TRIGGER documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
"""

PRODUCTS_TABLE_SQL = """
-- Products table for BM25 search examples (if pg_search available)
CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT,
    price NUMERIC(10, 2),
    data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Standard indexes
CREATE INDEX IF NOT EXISTS idx_products_category ON products (category);
CREATE INDEX IF NOT EXISTS idx_products_price ON products (price);
CREATE INDEX IF NOT EXISTS idx_products_data ON products USING GIN (data);

-- Trigram index for fuzzy product search
CREATE INDEX IF NOT EXISTS idx_products_name_trgm 
ON products USING GIN (name gin_trgm_ops);
"""

SAMPLE_DATA_SQL = """
-- Insert sample documents
INSERT INTO documents (title, content, metadata, tags) VALUES
    ('PostgreSQL Full-Text Search Guide', 
     'Learn how to implement full-text search in PostgreSQL using tsvector and tsquery. This guide covers indexing strategies and ranking functions.',
     '{"type": "tutorial", "difficulty": "intermediate"}',
     ARRAY['postgresql', 'search', 'tutorial']),
    ('Vector Similarity with pgvector',
     'pgvector enables storing and querying vector embeddings in PostgreSQL. Use HNSW or IVFFlat indexes for approximate nearest neighbor search.',
     '{"type": "tutorial", "difficulty": "advanced"}',
     ARRAY['postgresql', 'vectors', 'ai', 'embeddings']),
    ('JSONB Indexing Strategies',
     'Explore different indexing options for JSONB columns including GIN indexes, jsonb_path_ops, and expression indexes for specific fields.',
     '{"type": "reference", "difficulty": "intermediate"}',
     ARRAY['postgresql', 'jsonb', 'indexing'])
ON CONFLICT DO NOTHING;

-- Insert sample products
INSERT INTO products (name, description, category, price, data) VALUES
    ('Mechanical Keyboard', 'Cherry MX Blue switches, RGB backlight, USB-C', 'electronics', 149.99,
     '{"brand": "KeyTech", "in_stock": true, "features": ["rgb", "mechanical"]}'),
    ('Wireless Mouse', 'Ergonomic design, 6 buttons, 2.4GHz wireless', 'electronics', 49.99,
     '{"brand": "MouseCo", "in_stock": true, "features": ["wireless", "ergonomic"]}'),
    ('USB-C Hub', '7-in-1 hub with HDMI, USB-A, SD card reader', 'electronics', 39.99,
     '{"brand": "HubMax", "in_stock": false, "features": ["usb-c", "hdmi"]}')
ON CONFLICT DO NOTHING;
"""


def connect(host: str, port: int, dbname: str, user: str, password: str):
    """Create database connection."""
    return psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password
    )


def check_extensions(cur) -> dict:
    """Check which extensions are installed."""
    cur.execute("SELECT extname FROM pg_extension")
    return {row[0] for row in cur.fetchall()}


def execute_sql(cur, sql: str, description: str):
    """Execute SQL and report result."""
    print(f"\n{description}...")
    try:
        cur.execute(sql)
        print("  Done")
        return True
    except psycopg2.Error as e:
        print(f"  Error: {e.pgerror.strip() if e.pgerror else e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Create search-ready tables with FTS and vector support"
    )
    parser.add_argument("--host", default="localhost", help="Database host")
    parser.add_argument("--port", type=int, default=5432, help="Database port")
    parser.add_argument("--dbname", default="postgres", help="Database name")
    parser.add_argument("--user", default="postgres", help="Database user")
    parser.add_argument("--password", default="", help="Database password")
    parser.add_argument("--with-sample-data", action="store_true",
                        help="Insert sample data after creating tables")
    parser.add_argument("--drop-existing", action="store_true",
                        help="Drop existing tables before creating")
    args = parser.parse_args()

    print(f"Connecting to {args.host}:{args.port}/{args.dbname}...")
    
    try:
        conn = connect(args.host, args.port, args.dbname, args.user, args.password)
    except psycopg2.Error as e:
        print(f"Error: Could not connect: {e}")
        sys.exit(1)

    cur = conn.cursor()
    
    # Check extensions
    extensions = check_extensions(cur)
    print(f"\nInstalled extensions: {', '.join(sorted(extensions))}")
    
    if "vector" not in extensions:
        print("\nWarning: pgvector not installed. Vector columns will fail.")
        print("Run: CREATE EXTENSION vector;")
    
    if "pg_trgm" not in extensions:
        print("\nWarning: pg_trgm not installed. Trigram indexes will fail.")
        print("Run: CREATE EXTENSION pg_trgm;")
    
    # Drop existing tables if requested
    if args.drop_existing:
        print("\n--- Dropping Existing Tables ---")
        execute_sql(cur, "DROP TABLE IF EXISTS documents CASCADE", "Dropping documents table")
        execute_sql(cur, "DROP TABLE IF EXISTS products CASCADE", "Dropping products table")
        conn.commit()
    
    # Create tables
    print("\n--- Creating Tables and Indexes ---")
    
    success = execute_sql(cur, SCHEMA_SQL, "Creating documents table with indexes")
    if success:
        conn.commit()
    else:
        conn.rollback()
        print("Failed to create documents table")
    
    success = execute_sql(cur, PRODUCTS_TABLE_SQL, "Creating products table with indexes")
    if success:
        conn.commit()
    else:
        conn.rollback()
    
    # Insert sample data if requested
    if args.with_sample_data:
        print("\n--- Inserting Sample Data ---")
        success = execute_sql(cur, SAMPLE_DATA_SQL, "Inserting sample documents and products")
        if success:
            conn.commit()
        else:
            conn.rollback()
    
    # Verify tables
    print("\n--- Verification ---")
    cur.execute("""
        SELECT tablename FROM pg_tables 
        WHERE schemaname = 'public' AND tablename IN ('documents', 'products')
    """)
    tables = [row[0] for row in cur.fetchall()]
    print(f"Tables created: {', '.join(tables)}")
    
    cur.execute("""
        SELECT indexname FROM pg_indexes 
        WHERE schemaname = 'public' AND tablename IN ('documents', 'products')
    """)
    indexes = [row[0] for row in cur.fetchall()]
    print(f"Indexes created: {len(indexes)}")
    for idx in indexes:
        print(f"  - {idx}")
    
    # Row counts
    for table in tables:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"\n{table}: {count} rows")
    
    cur.close()
    conn.close()
    
    print("\nTable creation complete!")


if __name__ == "__main__":
    main()

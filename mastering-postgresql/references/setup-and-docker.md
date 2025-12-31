# Setup and Docker Reference

Local development environment, extension installation, and PostgreSQL configuration for search and vector workloads.

## Contents

- [Docker Compose Configurations](#docker-compose-configurations)
- [Extension Installation](#extension-installation)
- [PostgreSQL Configuration](#postgresql-configuration)
- [Development Workflow](#development-workflow)
- [psql Quick Reference](#psql-quick-reference)
- [Troubleshooting Setup](#troubleshooting-setup)

---

## Docker Compose Configurations

### pgvector Development Environment

```yaml
# docker-compose-pgvector.yml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg17
    container_name: postgres-dev
    environment:
      POSTGRES_USER: devuser
      POSTGRES_PASSWORD: devpass
      POSTGRES_DB: devdb
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init:/docker-entrypoint-initdb.d
    shm_size: '512mb'  # Production: increase to 2gb for parallel queries
    command: >
      postgres
      -c shared_buffers=256MB
      -c work_mem=16MB
      -c maintenance_work_mem=512MB
      -c max_parallel_workers_per_gather=2
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U devuser -d devdb"]
      interval: 10s
      timeout: 5s
      retries: 5

  pgadmin:
    image: dpage/pgadmin4:latest
    container_name: pgadmin
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@local.dev
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "8080:80"
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  postgres_data:
```

### ParadeDB Environment (BM25 Support)

```yaml
# docker-compose-paradedb.yml
version: '3.8'

services:
  paradedb:
    image: paradedb/paradedb:latest
    container_name: paradedb-dev
    environment:
      POSTGRES_USER: devuser
      POSTGRES_PASSWORD: devpass
      POSTGRES_DB: devdb
    ports:
      - "5432:5432"
    volumes:
      - paradedb_data:/var/lib/postgresql/data
    shm_size: '512mb'
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U devuser -d devdb"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  paradedb_data:
```

### Initialization Script

Create `init/01-extensions.sql`:

```sql
-- Enable extensions on database creation
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- For ParadeDB image only:
-- CREATE EXTENSION IF NOT EXISTS pg_search;
```

### Docker Commands

```bash
# Start environment
docker-compose -f docker-compose-pgvector.yml up -d

# View logs
docker-compose logs -f postgres

# Connect via psql
docker exec -it postgres-dev psql -U devuser -d devdb

# Stop and preserve data
docker-compose down

# Stop and remove data
docker-compose down -v
```

---

## Extension Installation

### pgvector

```sql
-- Check availability
SELECT * FROM pg_available_extensions WHERE name = 'vector';

-- Install
CREATE EXTENSION vector;

-- Verify
SELECT extversion FROM pg_extension WHERE extname = 'vector';
-- Should return: 0.8.0 or higher
```

### pg_trgm (Fuzzy Search)

```sql
CREATE EXTENSION pg_trgm;

-- Verify
SHOW pg_trgm.similarity_threshold;
-- Default: 0.3
```

### pg_search (BM25) - ParadeDB Only

```sql
-- Only available in ParadeDB image
CREATE EXTENSION pg_search;

-- Verify
SELECT * FROM pg_extension WHERE extname = 'pg_search';
```

### pg_stat_statements (Query Monitoring)

```sql
-- Requires postgresql.conf: shared_preload_libraries = 'pg_stat_statements'
CREATE EXTENSION pg_stat_statements;
```

### Extension Dependencies

| Extension | Requires | Notes |
|-----------|----------|-------|
| vector | None | pgvector/pgvector image has it pre-installed |
| pg_trgm | None | Included in contrib |
| pg_search | None | ParadeDB image only |
| pg_stat_statements | shared_preload_libraries | Requires restart |

---

## PostgreSQL Configuration

### Search-Optimized postgresql.conf

```ini
# Memory - adjust based on available RAM
shared_buffers = 256MB              # 25% of RAM for dedicated server
work_mem = 64MB                     # Per-operation memory for sorts/hashes
maintenance_work_mem = 512MB        # For index builds, VACUUM
effective_cache_size = 1GB          # Estimate of OS cache available

# Parallelism
max_parallel_workers_per_gather = 4
max_parallel_maintenance_workers = 4
max_parallel_workers = 8

# Planner - SSD settings
random_page_cost = 1.1              # 1.1 for SSD, 4.0 for HDD
effective_io_concurrency = 200      # 200 for SSD, 2 for HDD

# WAL - for better write performance
wal_buffers = 16MB
checkpoint_completion_target = 0.9

# Logging - development
log_min_duration_statement = 100    # Log queries over 100ms
log_statement = 'none'              # Set to 'all' for debugging
log_line_prefix = '%t [%p]: db=%d,user=%u '

# Statistics
default_statistics_target = 100     # Increase for complex queries
```

### Vector Workload Tuning

```ini
# For large vector index builds
maintenance_work_mem = 2GB          # More memory = faster HNSW build
max_parallel_maintenance_workers = 7

# Monitor progress
# SELECT * FROM pg_stat_progress_create_index;
```

### Full-Text Search Tuning

```ini
# Custom text search configuration (optional)
default_text_search_config = 'pg_catalog.english'
```

### Applying Configuration

```bash
# Docker: mount custom config
docker run -v ./postgresql.conf:/etc/postgresql/postgresql.conf \
  pgvector/pgvector:pg17 \
  postgres -c config_file=/etc/postgresql/postgresql.conf

# Or use -c flags in docker-compose command section
```

---

## Development Workflow

### Initial Setup Checklist

```
[ ] 1. Start Docker environment
[ ] 2. Verify PostgreSQL is healthy
[ ] 3. Create extensions
[ ] 4. Create application schema
[ ] 5. Create indexes
[ ] 6. Load sample data
[ ] 7. Test queries
[ ] 8. Verify index usage with EXPLAIN
```

### Sample Schema Creation

```sql
-- Documents with full-text search and vectors
CREATE TABLE documents (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT,
    metadata JSONB DEFAULT '{}',
    tags TEXT[] DEFAULT '{}',
    embedding vector(1536),
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(content, '')), 'B')
    ) STORED,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX idx_docs_search ON documents USING GIN (search_vector);
CREATE INDEX idx_docs_embedding ON documents USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_docs_metadata ON documents USING GIN (metadata jsonb_path_ops);
CREATE INDEX idx_docs_tags ON documents USING GIN (tags);
CREATE INDEX idx_docs_created ON documents (created_at DESC);

-- Updated timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### Data Volume Management

```bash
# Backup volume
docker run --rm -v postgres_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/postgres_backup.tar.gz /data

# Restore volume
docker run --rm -v postgres_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/postgres_backup.tar.gz -C /
```

---

## psql Quick Reference

Common commands for exploring PostgreSQL schemas and debugging.

### Meta-Commands

| Command | Description |
|---------|-------------|
| `\l` | List all databases |
| `\c dbname` | Connect to database |
| `\dt` | List tables in current schema |
| `\dt+` | List tables with sizes |
| `\d tablename` | Describe table structure |
| `\d+ tablename` | Describe with storage info |
| `\di` | List indexes |
| `\di+ tablename` | Index details for table |
| `\dx` | List installed extensions |
| `\df` | List functions |
| `\dn` | List schemas |
| `\du` | List roles/users |
| `\timing` | Toggle query timing display |
| `\x` | Toggle expanded output |
| `\q` | Quit psql |

### Schema Exploration

```sql
-- Check extensions and versions
\dx

-- Inspect table with indexes
\d+ documents

-- List all indexes on a table
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'documents';

-- Check index sizes
SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid))
FROM pg_stat_user_indexes
WHERE relname = 'documents';
```

### Query Analysis

```sql
-- Basic explain
EXPLAIN SELECT * FROM documents WHERE id = 1;

-- With execution stats (actually runs query)
EXPLAIN ANALYZE SELECT * FROM documents
WHERE search_vector @@ to_tsquery('postgresql');

-- Full analysis with buffers
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM documents
ORDER BY embedding <=> '[0.1,0.2,0.3]'::vector
LIMIT 10;
```

**Reading EXPLAIN output:**
- `Seq Scan`: Full table scan (may need index)
- `Index Scan`: Using index (good)
- `Bitmap Index Scan`: GIN/multiple conditions
- `actual time`: Real execution time in ms
- `rows`: Actual vs estimated row count

### Running Scripts

```bash
# Execute SQL file
psql -f schema.sql "postgresql://user:pass@localhost/mydb"

# Run single command
psql -c "SELECT version();" "postgresql://user:pass@localhost/mydb"

# Interactive with connection string
psql "postgresql://user:pass@localhost:5432/mydb"
```

---

## Troubleshooting Setup

### Extension Installation Failures

| Error | Cause | Solution |
|-------|-------|----------|
| `extension "vector" is not available` | Wrong image | Use `pgvector/pgvector:pg17` |
| `extension "pg_search" is not available` | Wrong image | Use `paradedb/paradedb` |
| `permission denied` | Not superuser | Connect as postgres user |
| `shared_preload_libraries` error | Config not loaded | Restart container after config change |

### Connection Issues

| Error | Cause | Solution |
|-------|-------|----------|
| `connection refused` | Container not running | `docker-compose up -d` |
| `password authentication failed` | Wrong credentials | Check POSTGRES_PASSWORD env var |
| `database does not exist` | DB not created | Check POSTGRES_DB env var |
| `too many connections` | Pool exhausted | Increase max_connections or use pooler |

### Performance Issues

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| Slow index build | Low maintenance_work_mem | Increase to 1-2GB |
| Slow queries | Missing indexes | Run EXPLAIN ANALYZE |
| High memory usage | shared_buffers too high | Reduce to 25% of container memory |
| Container OOM killed | shm_size too low | Increase shm_size (512mb dev, 2gb prod) |
| Slow parallel queries | shm_size insufficient | Increase to 2gb for production workloads |

### Verifying Setup

```sql
-- Check extensions
SELECT extname, extversion FROM pg_extension;

-- Check table indexes
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'documents';

-- Check index sizes
SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid))
FROM pg_stat_user_indexes WHERE relname = 'documents';

-- Test vector operations
SELECT '[1,2,3]'::vector <=> '[4,5,6]'::vector AS distance;

-- Test full-text search
SELECT to_tsvector('english', 'PostgreSQL is great') @@ 
       to_tsquery('english', 'postgresql');
```

### Container Health Check

```bash
# Check container status
docker-compose ps

# Check PostgreSQL logs for errors
docker-compose logs postgres | grep -i error

# Interactive shell for debugging
docker exec -it postgres-dev bash
```

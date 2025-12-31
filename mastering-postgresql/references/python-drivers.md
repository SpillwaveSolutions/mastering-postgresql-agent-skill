# Python Drivers Reference

Driver selection, connection patterns, pooling, and SQLAlchemy integration for PostgreSQL.

## Contents

- [Library Selection](#library-selection)
- [Connection Patterns](#connection-patterns)
- [SQLAlchemy Integration](#sqlalchemy-integration)
- [Error Handling](#error-handling)
- [Performance Optimization](#performance-optimization)

---

## Library Selection

| Library | Best For | Async | Performance |
|---------|----------|-------|-------------|
| **psycopg2** | Sync apps, stability | ❌ | Good |
| **psycopg3** | Modern sync/async | ✅ | Good |
| **asyncpg** | High-perf async | ✅ | Excellent |
| **SQLAlchemy** | ORM, portability | ✅ (2.0) | Good |

### Installation

```bash
# psycopg2 (binary for easy install)
pip install psycopg2-binary

# psycopg3
pip install "psycopg[binary,pool]"

# asyncpg
pip install asyncpg

# SQLAlchemy with async
pip install sqlalchemy[asyncio] asyncpg

# pgvector support
pip install pgvector
```

---

## Connection Patterns

### psycopg2 (Sync)

```python
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

# Single connection
conn = psycopg2.connect(
    host="localhost",
    dbname="mydb",
    user="user",
    password="pass"
)

# Context manager pattern
@contextmanager
def get_cursor(commit=True):
    conn = psycopg2.connect("postgresql://user:pass@localhost/mydb")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# Usage
with get_cursor() as cur:
    cur.execute("SELECT * FROM documents WHERE id = %s", (1,))
    result = cur.fetchone()
```

### psycopg2 Connection Pool

```python
from psycopg2 import pool

# Step 1: Create pool
connection_pool = pool.ThreadedConnectionPool(
    minconn=5,
    maxconn=20,
    host="localhost",
    dbname="mydb",
    user="user",
    password="pass"
)

# Step 2: Use pool
conn = connection_pool.getconn()
try:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM documents")
        results = cur.fetchall()
    conn.commit()
finally:
    connection_pool.putconn(conn)
```

### psycopg3 (Sync and Async)

```python
import psycopg
from psycopg.rows import dict_row

# Sync connection
with psycopg.connect("postgresql://user:pass@localhost/mydb", row_factory=dict_row) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM documents WHERE id = %s", (1,))
        result = cur.fetchone()

# Async connection
import asyncio
from psycopg import AsyncConnection

async def query_async():
    async with await AsyncConnection.connect(
        "postgresql://user:pass@localhost/mydb",
        row_factory=dict_row
    ) as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM documents")
            return await cur.fetchall()
```

### psycopg3 Connection Pool

```python
from psycopg_pool import ConnectionPool, AsyncConnectionPool

# Step 1: Create sync pool
pool = ConnectionPool(
    "postgresql://user:pass@localhost/mydb",
    min_size=5,
    max_size=20
)

# Step 2: Use sync pool
with pool.connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT 1")

# Async pool
async def main():
    # Step 1: Create async pool
    pool = AsyncConnectionPool(
        "postgresql://user:pass@localhost/mydb",
        min_size=5,
        max_size=20
    )
    await pool.open()
    
    # Step 2: Use async pool
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1")
    
    # Step 3: Close when done
    await pool.close()
```

### psycopg3 Pool with pgvector Type Registration

Use the `configure` callback to register pgvector types on every connection:

```python
from psycopg_pool import AsyncConnectionPool
from pgvector.psycopg import register_vector

async def configure_connection(conn):
    """Configure every connection with pgvector types."""
    await register_vector(conn)

pool = AsyncConnectionPool(
    "postgresql://user:pass@localhost/mydb",
    min_size=5,
    max_size=20,
    configure=configure_connection,
    open=False  # Required for async pools
)
```

### FastAPI Lifespan Integration

The recommended pattern for managing pool lifecycle in FastAPI:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from psycopg_pool import AsyncConnectionPool
from pgvector.psycopg import register_vector

async def configure_conn(conn):
    await register_vector(conn)

pool = AsyncConnectionPool(
    conninfo="postgresql://user:pass@localhost/mydb",
    min_size=5,
    max_size=20,
    configure=configure_conn,
    open=False
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open pool on startup, close on shutdown."""
    await pool.open()
    yield
    await pool.close()

app = FastAPI(lifespan=lifespan)

async def get_db():
    """Dependency for route handlers."""
    async with pool.connection() as conn:
        yield conn

@app.get("/search")
async def search(q: str, conn=Depends(get_db)):
    return await conn.fetch("SELECT * FROM docs WHERE ...")
```

### Pool Health Checking (psycopg3 3.2+)

For production reliability, configure pools to verify connections before serving:

```python
from psycopg_pool import ConnectionPool, AsyncConnectionPool

# Sync pool with built-in health check
pool = ConnectionPool(
    "postgresql://user:pass@localhost/mydb",
    min_size=5,
    max_size=20,
    check=ConnectionPool.check_connection,  # Validates before serving
    max_lifetime=3600.0,   # Close connections after 1 hour
    max_idle=600.0         # Close idle connections after 10 minutes
)

# Async pool with health check
async_pool = AsyncConnectionPool(
    "postgresql://user:pass@localhost/mydb",
    min_size=5,
    max_size=20,
    check=AsyncConnectionPool.check_connection,
    max_lifetime=3600.0,
    max_idle=600.0,
    open=False
)
```

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `check` | None | Callback to validate connection health before serving |
| `max_lifetime` | 3600s | Maximum connection age before replacement |
| `max_idle` | 600s | Close connections idle longer than this |
| `reconnect_timeout` | 300s | Max time to retry failed connections |

**When to use health checks:**
- Production deployments with load balancers
- Databases with `idle_session_timeout` configured
- Environments where connections may be dropped (cloud, firewalls)

### asyncpg (Async Only)

```python
import asyncpg

# Single connection
conn = await asyncpg.connect("postgresql://user:pass@localhost/mydb")
row = await conn.fetchrow("SELECT * FROM documents WHERE id = $1", 1)
await conn.close()

# Connection pool (recommended)
# Step 1: Create pool
pool = await asyncpg.create_pool(
    "postgresql://user:pass@localhost/mydb",
    min_size=5,
    max_size=20,
    command_timeout=60,
    statement_cache_size=100
)

# Step 2: Use pool
async with pool.acquire() as conn:
    rows = await conn.fetch("SELECT * FROM documents LIMIT 10")

# Step 3: Close when done
await pool.close()

# Verify pool is working:
# async with pool.acquire() as conn:
#     result = await conn.fetchval("SELECT 1")
#     assert result == 1
```

---

## SQLAlchemy Integration

### Setup with pgvector

```python
from sqlalchemy import Column, Integer, String, Text, create_engine
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, TSVECTOR
from sqlalchemy.orm import declarative_base, sessionmaker
from pgvector.sqlalchemy import Vector

Base = declarative_base()

class Document(Base):
    __tablename__ = 'documents'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    content = Column(Text)
    metadata = Column(JSONB, default={})
    tags = Column(ARRAY(String), default=[])
    embedding = Column(Vector(1536))
    search_vector = Column(TSVECTOR)

# Sync engine
engine = create_engine("postgresql+psycopg2://user:pass@localhost/mydb")

# Async engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
async_engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/mydb")
```

### Vector Queries with SQLAlchemy

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

def find_similar(session: Session, embedding: list, limit: int = 10):
    stmt = (
        select(Document)
        .order_by(Document.embedding.cosine_distance(embedding))
        .limit(limit)
    )
    return session.scalars(stmt).all()

# Async version
from sqlalchemy.ext.asyncio import AsyncSession

async def find_similar_async(session: AsyncSession, embedding: list, limit: int = 10):
    stmt = (
        select(Document)
        .order_by(Document.embedding.cosine_distance(embedding))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()
```

### Full-Text Search with SQLAlchemy

```python
from sqlalchemy import func

def search_documents(session: Session, query: str, limit: int = 20):
    ts_query = func.websearch_to_tsquery('english', query)
    stmt = (
        select(
            Document,
            func.ts_rank(Document.search_vector, ts_query).label('rank')
        )
        .where(Document.search_vector.op('@@')(ts_query))
        .order_by(func.ts_rank(Document.search_vector, ts_query).desc())
        .limit(limit)
    )
    return session.execute(stmt).all()
```

### Bulk Operations with SQLAlchemy

```python
from sqlalchemy.dialects.postgresql import insert

# Bulk upsert
stmt = insert(Document).values([
    {"title": "Doc 1", "content": "Content 1"},
    {"title": "Doc 2", "content": "Content 2"},
])
stmt = stmt.on_conflict_do_update(
    index_elements=['title'],
    set_={"content": stmt.excluded.content}
)
session.execute(stmt)
session.commit()
```

---

## Error Handling

### Retry Pattern

```python
import asyncio
from functools import wraps
import asyncpg

def with_retry(max_attempts=3, delay=1.0, backoff=2.0):
    """Decorator for automatic retry on connection errors."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except (asyncpg.PostgresConnectionError, 
                        asyncpg.InterfaceError) as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(delay * (backoff ** attempt))
            raise last_exception
        return wrapper
    return decorator

@with_retry(max_attempts=3)
async def query_with_retry(pool, query, *args):
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)
```

### Connection Recovery

```python
class DatabasePool:
    """Self-healing connection pool wrapper."""
    
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool = None
    
    async def get_pool(self):
        if self.pool is None or self.pool._closed:
            self.pool = await asyncpg.create_pool(
                self.dsn,
                min_size=5,
                max_size=20
            )
        return self.pool
    
    async def execute(self, query: str, *args):
        pool = await self.get_pool()
        try:
            async with pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except asyncpg.InterfaceError:
            # Pool corrupted, recreate
            await self.pool.close()
            self.pool = None
            return await self.execute(query, *args)
```

---

## Performance Optimization

### Prepared Statements

```python
# asyncpg auto-caches prepared statements
# Explicit preparation for hot paths:
stmt = await conn.prepare("SELECT * FROM documents WHERE id = $1")
for doc_id in doc_ids:
    row = await stmt.fetchrow(doc_id)
```

### Pipeline Mode (psycopg3)

```python
# Reduce round trips for multiple queries
async with conn.pipeline():
    await conn.execute("INSERT INTO logs (msg) VALUES ($1)", ("msg1",))
    await conn.execute("INSERT INTO logs (msg) VALUES ($1)", ("msg2",))
    await conn.execute("INSERT INTO logs (msg) VALUES ($1)", ("msg3",))
# All executed in single round trip
```

### Connection Pool Sizing

```
Rule of thumb:
max_connections = (core_count * 2) + effective_spindle_count

For SSD:
- Web app: 10-20 connections per app instance
- Background workers: 2-5 per worker

Total: Keep under PostgreSQL max_connections (default 100)
```

### Query Optimization Tips

```python
# 1. Use LIMIT with ORDER BY for vector search
# Bad: fetches all then limits in Python
rows = await conn.fetch("SELECT * FROM docs ORDER BY embedding <=> $1", emb)
results = rows[:10]

# Good: limits in query (uses index)
rows = await conn.fetch("""
    SELECT * FROM docs ORDER BY embedding <=> $1 LIMIT 10
""", emb)

# 2. Avoid SELECT * with large columns (like embedding)
# Bad
rows = await conn.fetch("SELECT * FROM docs WHERE id = $1", doc_id)

# Good
rows = await conn.fetch("""
    SELECT id, title, created_at FROM docs WHERE id = $1
""", doc_id)

# 3. Use EXISTS for presence checks
# Bad
count = await conn.fetchval("SELECT COUNT(*) FROM docs WHERE user_id = $1", uid)
exists = count > 0

# Good
exists = await conn.fetchval("""
    SELECT EXISTS(SELECT 1 FROM docs WHERE user_id = $1)
""", uid)
```

---

## Related References

- [python-queries.md](python-queries.md) — Bulk inserts, FTS queries, vector queries, JSONB operations

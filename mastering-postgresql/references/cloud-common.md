# Cloud Common Reference

Extension availability, connection pooling patterns, production configuration, and cost optimization.

## Contents

- [Extension Availability Matrix](#extension-availability-matrix)
- [Connection Pooling](#connection-pooling)
- [Production Configuration](#production-configuration)
- [Monitoring Queries](#monitoring-queries)
- [Cost Optimization](#cost-optimization)

---

## Extension Availability Matrix

| Extension | AWS RDS | AWS Aurora | GCP Cloud SQL | GCP AlloyDB | Azure Flexible | Neon | Supabase |
|-----------|---------|------------|---------------|-------------|----------------|------|----------|
| **pgvector** | 0.8.0 | 0.8.0 | 0.8.0 | Native | 0.8.0 | Yes | Yes |
| **pg_diskann** | No | No | No | No | GA | No | No |
| **alloydb_scann** | No | No | No | Yes | No | No | No |
| **pg_trgm** | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| **pg_search (BM25)** | No | No | No | No | No | Yes | Yes |
| **pg_stat_statements** | Yes | Yes | Yes | Yes | Yes | Yes | Yes |

**Notes:**
- pg_search/BM25 requires self-hosted PostgreSQL, ParadeDB, Neon, or Supabase
- pg_diskann (Azure) and alloydb_scann (GCP) are cloud-specific optimized vector indexes

---

## Connection Pooling

### Pooling Options by Platform

| Platform | Built-in | External Option |
|----------|----------|-----------------|
| AWS RDS | RDS Proxy | PgBouncer on EC2 |
| AWS Aurora | RDS Proxy | - |
| GCP Cloud SQL | No | PgBouncer, Pgpool-II |
| GCP AlloyDB | No | PgBouncer |
| Azure Flexible | PgBouncer | - |
| Neon | Built-in | - |
| Supabase | Built-in | - |

### PgBouncer Configuration (Self-Managed)

```ini
# pgbouncer.ini
[databases]
mydb = host=db-host port=5432 dbname=mydb

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 20
min_pool_size = 5
reserve_pool_size = 5
```

### Application-Side Pooling

```python
# asyncpg pool (always recommended)
pool = await asyncpg.create_pool(
    dsn,
    min_size=5,
    max_size=20,
    max_inactive_connection_lifetime=300,
    command_timeout=60
)

# When using PgBouncer, disable prepared statements
pool = await asyncpg.create_pool(
    dsn,
    min_size=5,
    max_size=20,
    statement_cache_size=0  # Required for PgBouncer transaction mode
)
```

---

## Production Configuration

### Recommended Parameters

```sql
-- Memory (adjust based on instance size)
ALTER SYSTEM SET shared_buffers = '4GB';          -- 25% of RAM
ALTER SYSTEM SET effective_cache_size = '12GB';   -- 75% of RAM
ALTER SYSTEM SET work_mem = '256MB';
ALTER SYSTEM SET maintenance_work_mem = '1GB';

-- Connections
ALTER SYSTEM SET max_connections = 200;

-- Vector workloads
ALTER SYSTEM SET max_parallel_workers_per_gather = 4;
ALTER SYSTEM SET max_parallel_maintenance_workers = 4;

-- WAL
ALTER SYSTEM SET wal_buffers = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;

-- Reload
SELECT pg_reload_conf();
```

### Memory Sizing Guidelines

| RAM | shared_buffers | effective_cache_size | work_mem |
|-----|----------------|---------------------|----------|
| 4GB | 1GB | 3GB | 64MB |
| 8GB | 2GB | 6GB | 128MB |
| 16GB | 4GB | 12GB | 256MB |
| 32GB | 8GB | 24GB | 512MB |

---

## Monitoring Queries

### Active Connections

```sql
SELECT datname, state, count(*)
FROM pg_stat_activity
GROUP BY datname, state;
```

### Slow Queries

```sql
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
```

### Index Usage

```sql
SELECT relname, seq_scan, idx_scan,
       round(100.0 * idx_scan / nullif(seq_scan + idx_scan, 0), 2) AS idx_pct
FROM pg_stat_user_tables
WHERE n_live_tup > 1000
ORDER BY seq_scan DESC;
```

### Table Bloat

```sql
SELECT relname,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
       n_dead_tup,
       last_autovacuum
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 10;
```

---

## Cost Optimization

### Instance Sizing Guidelines

| Workload | AWS | GCP | Azure |
|----------|-----|-----|-------|
| Dev/Test | db.t3.medium | db-f1-micro | B1ms |
| Small Prod | db.r6g.large | db-custom-2-8192 | D2s_v3 |
| Medium Prod | db.r6g.xlarge | db-custom-4-16384 | D4s_v3 |
| Large Vector | db.r6g.2xlarge | db-custom-8-32768 | D8s_v3 |

### Cost-Saving Strategies

1. **Use Reserved Instances** - 30-60% savings for 1-3 year commitment
2. **Aurora Serverless v2** - Scale to zero during low usage
3. **Read Replicas** - Offload read queries
4. **Storage Optimization** - Use gp3 on AWS, adjust IOPS as needed
5. **Right-size Connections** - Reduce max_connections if not needed
6. **Neon/Supabase for dev** - Scale-to-zero eliminates idle costs

### Storage Costs

| Provider | Storage | Approximate Cost |
|----------|---------|------------------|
| AWS RDS | gp3 | $0.08/GB/month |
| AWS Aurora | Auto | $0.10/GB/month |
| GCP Cloud SQL | SSD | $0.17/GB/month |
| GCP AlloyDB | Auto | $0.10/GB/month |
| Azure | Premium SSD | $0.12/GB/month |

### Vector Index Storage Estimate

```
HNSW index size ≈ rows × dimensions × 4 bytes × 1.5 (overhead)

Example: 1M rows × 1536 dims × 4 × 1.5 = ~9.2 GB

IVFFlat index size ≈ rows × dimensions × 4 bytes × 1.1

DiskANN: Uses disk storage, minimal RAM overhead
```

---

## Related References

- [cloud-aws.md](cloud-aws.md) - AWS RDS and Aurora
- [cloud-gcp.md](cloud-gcp.md) - GCP Cloud SQL and AlloyDB
- [cloud-azure.md](cloud-azure.md) - Azure Flexible Server
- [cloud-serverless.md](cloud-serverless.md) - Neon and Supabase

# Cloud Deployments Reference

Production deployment on AWS, GCP, and Azure with PostgreSQL search and vector capabilities.

## Contents

- [Extension Availability Matrix](#extension-availability-matrix)
- [AWS RDS and Aurora](#aws-rds-and-aurora)
- [GCP Cloud SQL](#gcp-cloud-sql)
- [GCP AlloyDB](#gcp-alloydb)
- [Azure Database for PostgreSQL](#azure-database-for-postgresql)
- [Connection Pooling](#connection-pooling)
- [Production Configuration](#production-configuration)
- [Cost Optimization](#cost-optimization)

---

## Extension Availability Matrix

| Extension | AWS RDS | AWS Aurora | GCP Cloud SQL | GCP AlloyDB | Azure Flexible |
|-----------|---------|------------|---------------|-------------|----------------|
| **pgvector** | 0.8.0 | 0.8.0 | 0.8.0 | ✅ (native) | 0.8.0 |
| **pg_diskann** | ❌ | ❌ | ❌ | ❌ | ✅ (GA) |
| **alloydb_scann** | ❌ | ❌ | ❌ | ✅ | ❌ |
| **pg_trgm** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **pg_search (BM25)** | ❌ | ❌ | ❌ | ❌ | ❌ |
| **pg_stat_statements** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **uuid-ossp** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **hstore** | ✅ | ✅ | ✅ | ✅ | ✅ |

**Notes:**
- pg_search/BM25 requires self-hosted PostgreSQL or ParadeDB managed service
- pg_diskann (Azure) and alloydb_scann (GCP) are cloud-specific optimized vector indexes

---

## AWS RDS and Aurora

### Create RDS PostgreSQL Instance

```bash
# Create parameter group for extensions
aws rds create-db-parameter-group \
  --db-parameter-group-name pg-vector-params \
  --db-parameter-group-family postgres16 \
  --description "PostgreSQL with vector extensions"

# Modify for pg_stat_statements
aws rds modify-db-parameter-group \
  --db-parameter-group-name pg-vector-params \
  --parameters "ParameterName=shared_preload_libraries,ParameterValue=pg_stat_statements,ApplyMethod=pending-reboot"

# Create RDS instance
aws rds create-db-instance \
  --db-instance-identifier mydb-postgres \
  --db-instance-class db.r6g.large \
  --engine postgres \
  --engine-version 16.4 \
  --allocated-storage 100 \
  --storage-type gp3 \
  --storage-throughput 125 \
  --master-username postgres \
  --master-user-password 'YourSecurePassword123!' \
  --db-parameter-group-name pg-vector-params \
  --vpc-security-group-ids sg-xxxxxxxx \
  --db-subnet-group-name mydb-subnet-group \
  --multi-az \
  --backup-retention-period 7 \
  --publicly-accessible false
```

### Create Aurora PostgreSQL Cluster

```bash
# Aurora Serverless v2 (recommended for variable workloads)
aws rds create-db-cluster \
  --db-cluster-identifier mydb-aurora \
  --engine aurora-postgresql \
  --engine-version 16.4 \
  --master-username postgres \
  --master-user-password 'YourSecurePassword123!' \
  --serverless-v2-scaling-configuration MinCapacity=0.5,MaxCapacity=16 \
  --vpc-security-group-ids sg-xxxxxxxx \
  --db-subnet-group-name mydb-subnet-group

# Add instance to cluster
aws rds create-db-instance \
  --db-instance-identifier mydb-aurora-instance-1 \
  --db-cluster-identifier mydb-aurora \
  --db-instance-class db.serverless \
  --engine aurora-postgresql
```

### Enable pgvector on RDS/Aurora

```sql
-- Connect to database
CREATE EXTENSION vector;
CREATE EXTENSION pg_trgm;
CREATE EXTENSION pg_stat_statements;

-- Verify
SELECT extname, extversion FROM pg_extension;
```

### RDS Proxy Setup

```bash
# Create secret for credentials
aws secretsmanager create-secret \
  --name mydb-credentials \
  --secret-string '{"username":"postgres","password":"YourSecurePassword123!"}'

# Create RDS Proxy
aws rds create-db-proxy \
  --db-proxy-name mydb-proxy \
  --engine-family POSTGRESQL \
  --auth Description="Proxy auth",AuthScheme=SECRETS,SecretArn=arn:aws:secretsmanager:... \
  --role-arn arn:aws:iam::123456789:role/rds-proxy-role \
  --vpc-subnet-ids subnet-xxx subnet-yyy \
  --require-tls

# Register target
aws rds register-db-proxy-targets \
  --db-proxy-name mydb-proxy \
  --db-instance-identifiers mydb-postgres
```

### Connection String (AWS)

```python
# Direct connection
conn_string = "postgresql://postgres:password@mydb-postgres.xxxxx.us-east-1.rds.amazonaws.com:5432/mydb"

# Via RDS Proxy
conn_string = "postgresql://postgres:password@mydb-proxy.proxy-xxxxx.us-east-1.rds.amazonaws.com:5432/mydb"

# With SSL (recommended)
conn_string = "postgresql://postgres:password@host:5432/mydb?sslmode=require"
```

---

## GCP Cloud SQL

### Create Cloud SQL Instance

```bash
# Create instance
gcloud sql instances create mydb-cloudsql \
  --database-version=POSTGRES_16 \
  --tier=db-custom-4-16384 \
  --region=us-central1 \
  --availability-type=REGIONAL \
  --storage-type=SSD \
  --storage-size=100GB \
  --storage-auto-increase \
  --backup-start-time=02:00 \
  --maintenance-window-day=SUN \
  --maintenance-window-hour=03

# Set root password
gcloud sql users set-password postgres \
  --instance=mydb-cloudsql \
  --password='YourSecurePassword123!'

# Create database
gcloud sql databases create mydb --instance=mydb-cloudsql
```

### Enable Extensions on Cloud SQL

```bash
# Enable pgvector via database flags
gcloud sql instances patch mydb-cloudsql \
  --database-flags=cloudsql.enable_pgvector=on

# For pg_stat_statements
gcloud sql instances patch mydb-cloudsql \
  --database-flags=cloudsql.enable_pg_stat_statements=on
```

Then in SQL:

```sql
CREATE EXTENSION vector;
CREATE EXTENSION pg_trgm;
```

### Cloud SQL Proxy

```bash
# Install proxy
curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.0/cloud-sql-proxy.linux.amd64
chmod +x cloud-sql-proxy

# Run proxy
./cloud-sql-proxy --port 5432 PROJECT_ID:REGION:INSTANCE_NAME

# Or with IAM authentication
./cloud-sql-proxy --auto-iam-authn PROJECT_ID:REGION:INSTANCE_NAME
```

### Connection String (GCP)

```python
# Via Cloud SQL Proxy (localhost)
conn_string = "postgresql://postgres:password@127.0.0.1:5432/mydb"

# Direct private IP (within VPC)
conn_string = "postgresql://postgres:password@10.x.x.x:5432/mydb"

# With Cloud SQL Python Connector
from google.cloud.sql.connector import Connector

connector = Connector()
conn = connector.connect(
    "project:region:instance",
    "asyncpg",
    user="postgres",
    password="password",
    db="mydb"
)
```

---

## GCP AlloyDB

AlloyDB offers superior vector performance with ScaNN indexes.

### Create AlloyDB Cluster

```bash
# Create cluster
gcloud alloydb clusters create mydb-alloydb \
  --region=us-central1 \
  --password='YourSecurePassword123!' \
  --network=default

# Create primary instance
gcloud alloydb instances create mydb-primary \
  --cluster=mydb-alloydb \
  --region=us-central1 \
  --instance-type=PRIMARY \
  --cpu-count=4
```

### Enable pgvector and ScaNN on AlloyDB

```sql
-- pgvector is pre-installed, just enable
CREATE EXTENSION vector;

-- Enable ScaNN (AlloyDB optimized index)
CREATE EXTENSION alloydb_scann CASCADE;
```

### ScaNN Index (AlloyDB Exclusive)

ScaNN provides **10x faster index builds** and **4x faster queries** compared to HNSW.

```sql
-- Create ScaNN index
CREATE INDEX ON documents 
  USING scann (embedding cosine)
  WITH (num_leaves=100);

-- With automatic tuning
CREATE INDEX ON documents 
  USING scann (embedding cosine)
  WITH (mode='AUTO');
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `num_leaves` | Auto | Number of partitions. More = better recall, slower |
| `mode` | None | `AUTO` lets AlloyDB optimize |

### AlloyDB Vector Query

```sql
-- Same query syntax as pgvector
SELECT id, title, embedding <=> $1::vector AS distance
FROM documents
ORDER BY embedding <=> $1::vector
LIMIT 10;
```

### Connection String (AlloyDB)

```python
# Via AlloyDB Auth Proxy
./alloydb-auth-proxy "projects/PROJECT/locations/REGION/clusters/CLUSTER/instances/INSTANCE"

conn_string = "postgresql://postgres:password@127.0.0.1:5432/mydb"

# With Python Connector
from google.cloud.alloydb.connector import Connector

connector = Connector()
conn = await connector.connect_async(
    "projects/project/locations/region/clusters/cluster/instances/instance",
    "asyncpg",
    user="postgres",
    password="password",
    db="mydb"
)
```

---

## Azure Database for PostgreSQL

### Create Flexible Server

```bash
# Create resource group
az group create --name mydb-rg --location eastus

# Create flexible server
az postgres flexible-server create \
  --resource-group mydb-rg \
  --name mydb-postgres \
  --location eastus \
  --admin-user postgres \
  --admin-password 'YourSecurePassword123!' \
  --sku-name Standard_D4s_v3 \
  --tier GeneralPurpose \
  --storage-size 128 \
  --version 16 \
  --high-availability ZoneRedundant
```

### Enable Extensions on Azure

```bash
# Allow extensions
az postgres flexible-server parameter set \
  --resource-group mydb-rg \
  --server-name mydb-postgres \
  --name azure.extensions \
  --value "vector,pg_trgm,pg_stat_statements"
```

Then in SQL:

```sql
CREATE EXTENSION vector;
CREATE EXTENSION pg_trgm;
```

### pg_diskann Index (Azure Exclusive)

DiskANN is Microsoft's disk-based vector index, now GA on Azure PostgreSQL.

**Advantages over HNSW:**
- 32x lower memory footprint (stores index on SSD)
- Up to 10x lower latency at 95% recall
- 4x lower cost due to reduced compute requirements
- Scales to billions of vectors without RAM constraints

```bash
# Enable in Azure Portal: Server parameters -> azure.extensions
# Add both: VECTOR,DISKANN
```

```sql
-- Enable both extensions
CREATE EXTENSION vector;
CREATE EXTENSION diskann;

-- Create DiskANN index
CREATE INDEX idx_docs_diskann ON documents
  USING diskann (embedding vector_cosine_ops);

-- Query uses same syntax as pgvector
SELECT id, title, embedding <=> $1::vector AS distance
FROM documents
ORDER BY embedding <=> $1::vector
LIMIT 10;
```

| Factor | HNSW | DiskANN |
|--------|------|---------|
| Memory | High (in-RAM) | Low (disk-based) |
| Scale | Millions | Billions |
| Build speed | Slower | Faster |
| Best for | Performance-critical | Cost-sensitive, large scale |

### Enable Built-in PgBouncer

```bash
# Enable PgBouncer
az postgres flexible-server parameter set \
  --resource-group mydb-rg \
  --server-name mydb-postgres \
  --name pgbouncer.enabled \
  --value true

# Configure pool mode
az postgres flexible-server parameter set \
  --resource-group mydb-rg \
  --server-name mydb-postgres \
  --name pgbouncer.default_pool_size \
  --value 50
```

### Connection String (Azure)

```python
# Direct connection (port 5432)
conn_string = "postgresql://postgres:password@mydb-postgres.postgres.database.azure.com:5432/mydb?sslmode=require"

# Via PgBouncer (port 6432)
conn_string = "postgresql://postgres:password@mydb-postgres.postgres.database.azure.com:6432/mydb?sslmode=require"
```

---

## Connection Pooling

### Pooling Options by Platform

| Platform | Built-in | External Option |
|----------|----------|-----------------|
| AWS RDS | RDS Proxy | PgBouncer on EC2 |
| AWS Aurora | RDS Proxy | - |
| GCP Cloud SQL | ❌ | PgBouncer, Pgpool-II |
| GCP AlloyDB | ❌ | PgBouncer |
| Azure Flexible | PgBouncer | - |

### PgBouncer Configuration

For self-managed PgBouncer:

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

### Monitoring Queries

```sql
-- Active connections
SELECT datname, state, count(*) 
FROM pg_stat_activity 
GROUP BY datname, state;

-- Slow queries
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;

-- Index usage
SELECT relname, seq_scan, idx_scan,
       round(100.0 * idx_scan / nullif(seq_scan + idx_scan, 0), 2) AS idx_pct
FROM pg_stat_user_tables
WHERE n_live_tup > 1000
ORDER BY seq_scan DESC;
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
```

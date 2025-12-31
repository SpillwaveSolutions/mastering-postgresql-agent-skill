# GCP Cloud SQL and AlloyDB Reference

PostgreSQL deployment on GCP Cloud SQL and AlloyDB with pgvector and ScaNN support.

## Contents

- [Cloud SQL Instance](#cloud-sql-instance)
- [Enable Extensions on Cloud SQL](#enable-extensions-on-cloud-sql)
- [Cloud SQL Proxy](#cloud-sql-proxy)
- [AlloyDB Cluster](#alloydb-cluster)
- [ScaNN Index (AlloyDB Exclusive)](#scann-index-alloydb-exclusive)
- [Connection Strings](#connection-strings)

---

## Cloud SQL Instance

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

---

## Enable Extensions on Cloud SQL

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

---

## Cloud SQL Proxy

```bash
# Install proxy
curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.0/cloud-sql-proxy.linux.amd64
chmod +x cloud-sql-proxy

# Run proxy
./cloud-sql-proxy --port 5432 PROJECT_ID:REGION:INSTANCE_NAME

# Or with IAM authentication
./cloud-sql-proxy --auto-iam-authn PROJECT_ID:REGION:INSTANCE_NAME
```

---

## AlloyDB Cluster

AlloyDB offers superior vector performance with ScaNN indexes.

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

---

## ScaNN Index (AlloyDB Exclusive)

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

### Vector Query (Same syntax as pgvector)

```sql
SELECT id, title, embedding <=> $1::vector AS distance
FROM documents
ORDER BY embedding <=> $1::vector
LIMIT 10;
```

---

## Connection Strings

### Cloud SQL

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

### AlloyDB

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

## Instance Sizing

| Workload | Cloud SQL Tier | AlloyDB vCPU |
|----------|----------------|--------------|
| Dev/Test | db-f1-micro | 2 |
| Small Prod | db-custom-2-8192 | 4 |
| Medium Prod | db-custom-4-16384 | 8 |
| Large Vector | db-custom-8-32768 | 16 |

---

## Related References

- [cloud-common.md](cloud-common.md) - Extension matrix, pooling, production config
- [cloud-aws.md](cloud-aws.md) - AWS RDS and Aurora
- [cloud-azure.md](cloud-azure.md) - Azure Flexible Server

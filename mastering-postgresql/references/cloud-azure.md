# Azure Database for PostgreSQL Reference

PostgreSQL deployment on Azure Flexible Server with pgvector and pg_diskann support.

## Contents

- [Create Flexible Server](#create-flexible-server)
- [Enable Extensions](#enable-extensions)
- [pg_diskann Index (Azure Exclusive)](#pg_diskann-index-azure-exclusive)
- [Enable Built-in PgBouncer](#enable-built-in-pgbouncer)
- [Connection Strings](#connection-strings)

---

## Create Flexible Server

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

---

## Enable Extensions

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

---

## pg_diskann Index (Azure Exclusive)

DiskANN is Microsoft's disk-based vector index, now GA on Azure PostgreSQL.

**Advantages over HNSW:**
- 32x lower memory footprint (stores index on SSD)
- Up to 10x lower latency at 95% recall
- 4x lower cost due to reduced compute requirements
- Scales to billions of vectors without RAM constraints

### Enable DiskANN

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

### HNSW vs DiskANN Comparison

| Factor | HNSW | DiskANN |
|--------|------|---------|
| Memory | High (in-RAM) | Low (disk-based) |
| Scale | Millions | Billions |
| Build speed | Slower | Faster |
| Best for | Performance-critical | Cost-sensitive, large scale |

---

## Enable Built-in PgBouncer

Azure Flexible Server includes built-in PgBouncer for connection pooling.

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

---

## Connection Strings

```python
# Direct connection (port 5432)
conn_string = "postgresql://postgres:password@mydb-postgres.postgres.database.azure.com:5432/mydb?sslmode=require"

# Via PgBouncer (port 6432)
conn_string = "postgresql://postgres:password@mydb-postgres.postgres.database.azure.com:6432/mydb?sslmode=require"
```

---

## Instance Sizing

| Workload | SKU | vCPU | RAM |
|----------|-----|------|-----|
| Dev/Test | B1ms | 1 | 2GB |
| Small Prod | D2s_v3 | 2 | 8GB |
| Medium Prod | D4s_v3 | 4 | 16GB |
| Large Vector | D8s_v3 | 8 | 32GB |

---

## Related References

- [cloud-common.md](cloud-common.md) - Extension matrix, pooling, production config
- [cloud-aws.md](cloud-aws.md) - AWS RDS and Aurora
- [cloud-gcp.md](cloud-gcp.md) - GCP Cloud SQL and AlloyDB

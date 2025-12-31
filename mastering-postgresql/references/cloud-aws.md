# AWS RDS and Aurora Reference

PostgreSQL deployment on AWS RDS and Aurora with pgvector support.

## Contents

- [Create RDS PostgreSQL Instance](#create-rds-postgresql-instance)
- [Create Aurora PostgreSQL Cluster](#create-aurora-postgresql-cluster)
- [Enable pgvector on RDS/Aurora](#enable-pgvector-on-rdsaurora)
- [RDS Proxy Setup](#rds-proxy-setup)
- [Connection Strings](#connection-strings)

---

## Create RDS PostgreSQL Instance

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

---

## Create Aurora PostgreSQL Cluster

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

---

## Enable pgvector on RDS/Aurora

```sql
-- Connect to database
CREATE EXTENSION vector;
CREATE EXTENSION pg_trgm;
CREATE EXTENSION pg_stat_statements;

-- Verify
SELECT extname, extversion FROM pg_extension;
```

---

## RDS Proxy Setup

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

---

## Connection Strings

```python
# Direct connection
conn_string = "postgresql://postgres:password@mydb-postgres.xxxxx.us-east-1.rds.amazonaws.com:5432/mydb"

# Via RDS Proxy
conn_string = "postgresql://postgres:password@mydb-proxy.proxy-xxxxx.us-east-1.rds.amazonaws.com:5432/mydb"

# With SSL (recommended)
conn_string = "postgresql://postgres:password@host:5432/mydb?sslmode=require"
```

---

## Instance Sizing

| Workload | Instance Type | vCPU | RAM |
|----------|---------------|------|-----|
| Dev/Test | db.t3.medium | 2 | 4GB |
| Small Prod | db.r6g.large | 2 | 16GB |
| Medium Prod | db.r6g.xlarge | 4 | 32GB |
| Large Vector | db.r6g.2xlarge | 8 | 64GB |

---

## Related References

- [cloud-common.md](cloud-common.md) - Extension matrix, pooling, production config
- [cloud-gcp.md](cloud-gcp.md) - GCP Cloud SQL and AlloyDB
- [cloud-azure.md](cloud-azure.md) - Azure Flexible Server

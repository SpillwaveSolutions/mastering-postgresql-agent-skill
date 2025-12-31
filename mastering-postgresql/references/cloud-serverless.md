# Serverless PostgreSQL Reference

Neon and Supabase for developer-focused PostgreSQL with scale-to-zero and instant branching.

## Contents

- [Neon](#neon)
- [Supabase](#supabase)
- [Serverless vs Traditional Managed](#serverless-vs-traditional-managed)
- [When to Choose Serverless](#when-to-choose-serverless)

---

## Neon

Scale-to-zero PostgreSQL with instant database branching.

### Connection

```bash
# Connect via connection string from Neon console
psql "postgresql://user:pass@ep-cool-name-123456.us-east-2.aws.neon.tech/neondb?sslmode=require"
```

### Enable Extensions

```sql
-- Enable pgvector (pre-installed)
CREATE EXTENSION vector;

-- Standard pgvector queries work as-is
SELECT * FROM documents ORDER BY embedding <=> $1::vector LIMIT 10;
```

### Key Features

| Feature | Description |
|---------|-------------|
| Scale-to-zero | No charges when idle (auto-suspend after 5 min) |
| Instant branching | Copy-on-write clones for CI/CD, previews, testing |
| Vercel integration | Auto-create branches per PR |
| pgvector | Pre-installed, no superuser restrictions |
| pg_search (BM25) | Available |

### Best For

- Development and testing environments
- Bursty workloads with idle periods
- CI/CD workflows (branch per PR)
- Cost-sensitive projects

---

## Supabase

Backend-as-a-Service with PostgreSQL, auth, real-time, and storage.

### Connection

```bash
# Connect via connection string from Supabase dashboard
psql "postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres"
```

### Enable Extensions

```sql
-- Enable pgvector
CREATE EXTENSION vector;

-- Supabase includes real-time subscriptions on tables
ALTER TABLE documents REPLICA IDENTITY FULL;
```

### Key Features

| Feature | Description |
|---------|-------------|
| BaaS bundle | Auth, real-time, storage, edge functions included |
| Auto-generated APIs | REST and GraphQL from schema |
| Git-integrated branching | Provisions DB + runs migrations |
| pgvector | Pre-installed for vector workloads |
| pg_search (BM25) | Available |

### Best For

- Full-stack applications
- Rapid prototyping
- Apps needing auth + real-time out of the box
- Teams wanting managed backend infrastructure

---

## Serverless vs Traditional Managed

| Factor | Neon/Supabase | AWS RDS/Aurora | GCP Cloud SQL | Azure Flexible |
|--------|---------------|----------------|---------------|----------------|
| Scale-to-zero | Yes | Aurora Serverless v2 only | No | No |
| Instant branching | Yes | No | No | No |
| Setup complexity | Low | Medium | Medium | Medium |
| Enterprise compliance | Growing | Full | Full | Full |
| Best for | Dev, startups | Enterprise | Enterprise | Enterprise |

---

## When to Choose Serverless

**Choose Neon when:**
- You need scale-to-zero for cost savings
- CI/CD requires database branches per PR
- Workloads are bursty with idle periods
- Development/staging environments

**Choose Supabase when:**
- You need auth, real-time, storage bundled
- Building full-stack apps quickly
- Want auto-generated REST/GraphQL APIs
- Need edge functions alongside database

**Choose Traditional Managed when:**
- Enterprise compliance requirements (SOC2, HIPAA)
- Predictable, high-volume workloads
- Need cloud-specific features (ScaNN, DiskANN)
- Existing cloud infrastructure integration

---

## Related References

- [cloud-common.md](cloud-common.md) - Extension matrix, pooling, production config
- [cloud-aws.md](cloud-aws.md) - AWS RDS and Aurora
- [cloud-gcp.md](cloud-gcp.md) - GCP Cloud SQL and AlloyDB
- [cloud-azure.md](cloud-azure.md) - Azure Flexible Server

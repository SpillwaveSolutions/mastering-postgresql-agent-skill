# Mastering PostgreSQL Agent Skill

PostgreSQL development for Python with full-text search (tsvector, tsquery, BM25 via pg_search), vector similarity (pgvector with HNSW/IVFFlat), JSONB and array indexing, and production deployment.

## Features

- **Full-text Search**: tsvector, tsquery, GIN indexes, ts_rank
- **BM25 Search**: pg_search/ParadeDB integration
- **Vector Similarity**: pgvector with HNSW and IVFFlat indexes
- **JSONB Indexing**: GIN indexes, containment queries
- **Python Drivers**: psycopg2, psycopg3, asyncpg, SQLAlchemy
- **Cloud Deployment**: AWS RDS/Aurora, GCP Cloud SQL/AlloyDB, Azure

## When to Use This Skill

Use this skill when:
- Creating search features with PostgreSQL
- Storing and querying AI embeddings
- Optimizing PostgreSQL indexes
- Setting up Docker development environments
- Deploying to cloud providers (AWS, GCP, Azure)

## Installing with Skilz (Universal Installer)

The recommended way to install this skill across different AI coding agents is using the **skilz** universal installer.

### Install Skilz

```bash
pip install skilz
```

This skill supports [Agent Skill Standard](https://agentskills.io/) which means it supports 14 plus coding agents including Claude Code, OpenAI Codex, Cursor and Gemini.

### Git URL Options

You can use either `-g` or `--git` with HTTPS or SSH URLs:

```bash
# HTTPS URL
skilz install -g https://github.com/SpillwaveSolutions/mastering-postgresql-agent-skill

# SSH URL
skilz install --git git@github.com:SpillwaveSolutions/mastering-postgresql-agent-skill.git
```

### Claude Code

Install to user home (available in all projects):
```bash
skilz install -g https://github.com/SpillwaveSolutions/mastering-postgresql-agent-skill
```

Install to current project only:
```bash
skilz install -g https://github.com/SpillwaveSolutions/mastering-postgresql-agent-skill --project
```

### OpenCode

Install for [OpenCode](https://opencode.ai):
```bash
skilz install -g https://github.com/SpillwaveSolutions/mastering-postgresql-agent-skill --agent opencode
```

Project-level install:
```bash
skilz install -g https://github.com/SpillwaveSolutions/mastering-postgresql-agent-skill --project --agent opencode
```

### Gemini

Project-level install for Gemini:
```bash
skilz install -g https://github.com/SpillwaveSolutions/mastering-postgresql-agent-skill --agent gemini
```

### OpenAI Codex

Install for OpenAI Codex:
```bash
skilz install -g https://github.com/SpillwaveSolutions/mastering-postgresql-agent-skill --agent codex
```

Project-level install:
```bash
skilz install -g https://github.com/SpillwaveSolutions/mastering-postgresql-agent-skill --project --agent codex
```

### Install from Skillzwave Marketplace

```bash
# Claude to user home dir ~/.claude/skills
skilz install SpillwaveSolutions_mastering-postgresql-agent-skill/mastering-postgresql

# Claude skill in project folder ./claude/skills
skilz install SpillwaveSolutions_mastering-postgresql-agent-skill/mastering-postgresql --project

# OpenCode install to user home dir ~/.config/opencode/skills
skilz install SpillwaveSolutions_mastering-postgresql-agent-skill/mastering-postgresql --agent opencode

# OpenCode project level
skilz install SpillwaveSolutions_mastering-postgresql-agent-skill/mastering-postgresql --agent opencode --project

# OpenAI Codex install to user home dir ~/.codex/skills
skilz install SpillwaveSolutions_mastering-postgresql-agent-skill/mastering-postgresql --agent codex

# OpenAI Codex project level ./.codex/skills
skilz install SpillwaveSolutions_mastering-postgresql-agent-skill/mastering-postgresql --agent codex --project

# Gemini CLI (project level) -- only works with project level
skilz install SpillwaveSolutions_mastering-postgresql-agent-skill/mastering-postgresql --agent gemini
```

See this site [skill Listing](https://skillzwave.ai/skill/SpillwaveSolutions__mastering-postgresql-agent-skill__mastering-postgresql__SKILL/) to see how to install this exact skill to 14+ different coding agents.

### Other Supported Agents

Skilz supports 14+ coding agents including Claude Code, OpenAI Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, Windsurf, Qwen Code, Aidr, and more.

For the full list of supported platforms, visit [SkillzWave.ai/platforms](https://skillzwave.ai/platforms/) or see the [skilz-cli GitHub repository](https://github.com/SpillwaveSolutions/skilz-cli)

## Skill Contents

```
mastering-postgresql/
├── SKILL.md           # Main skill documentation
├── references/        # Detailed reference guides
│   ├── setup-and-docker.md
│   ├── search-fulltext.md
│   ├── search-vectors-json.md
│   ├── python-drivers.md
│   ├── python-queries.md
│   └── cloud-deployments.md
├── scripts/           # Utility scripts
│   ├── setup_extensions.py
│   ├── create_search_tables.py
│   ├── bulk_operations.py
│   ├── health_check.py
│   ├── vector_search.py
│   ├── db_utils.py
│   └── requirements.txt
└── assets/            # Configuration templates
    ├── docker-compose-pgvector.yml
    ├── docker-compose-paradedb.yml
    ├── postgresql.conf
    └── schema-templates.sql
```

## Quick Start

After installing the skill, start with the Quick Start section in `mastering-postgresql/SKILL.md` to:

1. Start PostgreSQL with pgvector using Docker
2. Enable required extensions
3. Create searchable tables with vector columns
4. Query from Python using asyncpg

## License

MIT License

---

<a href="https://skillzwave.ai/">Largest Agentic Marketplace for AI Agent Skills</a> and
<a href="https://spillwave.com/">SpillWave: Leaders in AI Agent Development.</a>

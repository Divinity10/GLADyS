# Database Schema Management


**CRITICAL**: Local and Docker databases must stay in sync unless you have a specific reason to diverge.

## How It Works
- Migrations live in `src/db/migrations/` (numbered .sql files)
- Both `cli/local.py start` and `cli/docker.py start` run migrations automatically
- Use `--no-migrate` only if you intentionally need different schemas

## When Adding/Modifying Schema
1. Create migration in `src/db/migrations/` with next number (e.g., `009_new_feature.sql`)
2. Use `IF NOT EXISTS` / `IF EXISTS` for idempotency
3. Run `python cli/local.py migrate` to apply locally
4. Run `python cli/docker.py migrate` to apply to Docker
5. **Both environments must have the same schema** -- if you skip one, document why in working_memory.md

## Red Flags
- Test fails with "column does not exist" -> migration not applied
- Different behavior between local and Docker -> schema drift
- **Never assume migrations are applied** -- verify with `\d tablename` in psql if unsure

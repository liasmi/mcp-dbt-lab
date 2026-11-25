# Companion Guide — MCP Dev Testing, FreeLLMAPI Gateway, GitHub PR Flow, CI/CD & pre-commit

This document answers the four things you asked for:

1. The **built-in Python SDK tool** for testing an MCP server before connecting any client.
2. Setting up **[FreeLLMAPI](https://github.com/tashfeenahmed/freellmapi)** in its **own repo/folder**, with keys, **one `/v1` endpoint**, and **automatic switching when a provider hits its limit**.
3. Creating a GitHub repo from zero, working on a **branch**, opening a **PR**, merging, and adding **branch rules**.
4. What every step in **CI/CD** and **pre-commit** actually does.

> Main learning guide: [`MCP_DBT_LAB_GUIDE.md`](./MCP_DBT_LAB_GUIDE.md). Read step 9 there for the MCP server source code; this document explains how to *test* it.

---

## 0. Current state of `/Users/meliliismail/Documents/mcp-dbt-lab` (checked just now)

**Already there:** dbt project (`dbt_project.yml`, `profiles.yml`), SA/INT/CA models, seeds, macro, tests, Python seed loader, `uv.lock`, the two guides, and a working DuckDB database.

**Still missing:** `mcp_server/server.py` (folder is empty), `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, and a Git repository (`git status` says "not a git repository"). Also, `mcp dev` needs the CLI extra (`mcp[cli]`) — plain `mcp` refuses to run it.

Environment check: `node v24.21.0`, `npx 11.19.0`, `Docker 29.8.0` — so both the MCP Inspector and the FreeLLMAPI Docker install will work on this machine.

---

## Part 1 — Test your MCP server out of the box with `mcp dev`

### 1.1 What the "out of the box" feature is

The Python MCP SDK ships a CLI. Check it:

```bash
uv add "mcp[cli]"        # adds typer + CLI support (one time)
uv run mcp --help
```

You will see four commands:

| Command | What it does |
|---|---|
| `mcp version` | Print SDK version |
| `mcp dev <file>` | **Run the server with the official MCP Inspector UI** — this is the built-in test tool you were thinking of |
| `mcp run <file>` | Run the server over stdio directly (no UI) |
| `mcp install <file>` | Register the server in Claude Desktop |

> You can try it without changing `pyproject.toml`:
> `uv run --with 'mcp[cli]' mcp dev -e . mcp_server/server.py`

### 1.2 Copy the server file first

If `mcp_server/server.py` is still empty, copy the full server from **step 9.2 of the main guide** into that path. Then:

```bash
cd /Users/meliliismail/Documents/mcp-dbt-lab

# One-time: install CLI extras into the project
uv add "mcp[cli]"

# Launch the Inspector (needs Node/npx — available here)
uv run mcp dev -e . mcp_server/server.py
```

What `-e .` does: it installs your project (and its deps: `duckdb`, `python-dotenv`, …) into the temporary environment the Inspector uses to start your server. Without it, imports would fail.

The command starts the MCP Inspector; open the URL it prints (normally **http://127.0.0.1:6274**).

### 1.3 What to click in the Inspector

1. Transport: **STDIO**.
2. The command field is pre-filled by `mcp dev` (something like `uv run --with mcp --with-editable . mcp run mcp_server/server.py`).
3. Click **Connect** → the status turns green.
4. Open the **Tools** tab → **List Tools**. You should see:
   - `query_duckdb`
   - `list_dbt_models`
   - `get_model_sql`
   - `run_dbt`
5. Call them manually:
   - `query_duckdb` with `{"sql": "select count(*) as n from main.fct_orders"}` → expect `n | 5`.
   - `list_dbt_models` → expect `[sa] stg_orders, stg_customers`, `[int] int_customer_order_stats`, `[ca] dim_customers, fct_orders`.
   - `get_model_sql` with `{"model_name": "stg_orders"}` → returns the SQL.
   - `run_dbt` with `{"command": "parse"}` → returns dbt output.
6. Try a negative test: `run_dbt` with `{"command": "drop"}` → you should see a `ToolError` because of the whitelist.

### 1.4 Headless alternative (no browser)

This is the command already in the main guide — useful in CI or when you just want a list:

```bash
npx @modelcontextprotocol/inspector --cli \
  uv run mcp_server/server.py \
  --protocol-era modern --method tools/list
```

Run it again with `--protocol-era legacy` to check compatibility with older clients.

### 1.5 Golden rule (repeat)

A stdio MCP server speaks JSON-RPC on stdout. **Never `print()`** in the server — use `logging` to stderr. The example server does this correctly.

✅ **Checkpoint:** Inspector shows 4 tools and `query_duckdb` returns 5 rows.

---

## Part 2 — FreeLLMAPI: one endpoint, many free providers, automatic failover

Repo: <https://github.com/tashfeenahmed/freellmapi> (58k+ stars, MIT). It aggregates free tiers from 87 providers behind a single OpenAI-compatible `/v1` endpoint. The router picks a model, retries the next one on **429 / 5xx**, applies cooldowns and key rotation, encrypts provider keys at rest, and exposes one unified `freellmapi-…` key to your apps.

### 2.1 Keep it in a separate repo/folder

Yes — put it **outside** the dbt lab. Suggested layout:

```text
~/mcp-dbt-lab/        <- dbt + MCP server
~/freellmapi-src/     <- cloned gateway (this repo)
~/freellmapi/         <- Docker data (.env, SQLite volume) if you use the one-liner
```

### 2.2 Install (pick ONE)

**Option A — Docker Compose (recommended, Docker is installed):**

```bash
git clone https://github.com/tashfeenahmed/freellmapi.git ~/freellmapi-src
cd ~/freellmapi-src

ENCRYPTION_KEY="$(openssl rand -hex 32)"
printf 'ENCRYPTION_KEY=%s\nPORT=3001\n' "$ENCRYPTION_KEY" > .env

docker compose up -d
docker compose logs -f freellmapi
```

Dashboard: **http://localhost:3001**. API base: **http://localhost:3001/v1**.

**Option B — one-line installer:**

```bash
# Read it first if you like: curl -fsSL https://freellmapi.co/install.sh
curl -fsSL https://freellmapi.co/install.sh | bash
# creates ~/freellmapi, starts the container on port 3001
```

**Option C — from source without Docker (Node 20+):**

```bash
git clone https://github.com/tashfeenahmed/freellmapi.git ~/freellmapi-src
cd ~/freellmapi-src
npm install
ENCRYPTION_KEY="$(node -e 'console.log(require("crypto").randomBytes(32).toString("hex"))')"
printf 'ENCRYPTION_KEY=%s\nPORT=3001\n' "$ENCRYPTION_KEY" > .env
npm run dev
```

Dashboard: **http://localhost:5173**.

### 2.3 Add keys and build the fallback chain

1. Open the dashboard and create the admin account (server installs ask for email + password; the desktop app has none).
2. Go to **Keys** → add the provider keys you actually have (Groq, Google, OpenRouter, Cerebras, Mistral, etc.). You can also add a **custom** OpenAI-compatible endpoint (Ollama at `http://host.docker.internal:11434/v1`, LM Studio, vLLM).
3. Go to **Fallback Chain** and reorder models. This is the list the router walks when a model is rate-limited or errors.
4. Copy the **unified API key** from the Keys page header. It looks like `freellmapi-…`. This is the *only* key your apps see — provider keys stay encrypted in its SQLite DB.
5. Optional continuity: add to `~/freellmapi-src/.env` (or `~/freellmapi/.env`):
   ```env
   FREELLMAPI_CONTEXT_HANDOFF=on_model_switch
   ```
   When the router switches model mid-conversation, it injects a short handoff note so the new model continues instead of restarting.

### 2.4 Test the single endpoint

```bash
export FREELLMAPI_API_KEY='freellmapi-...'   # your copied key

# List models the router can serve
curl -sS http://localhost:3001/v1/models \
  -H "Authorization: Bearer $FREELLMAPI_API_KEY" | head -c 500

# One chat request; model "auto" = router chooses + fails over automatically
curl -sS http://localhost:3001/v1/chat/completions \
  -H "Authorization: Bearer $FREELLMAPI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"auto","messages":[{"role":"user","content":"Reply with exactly: OK"}]}'
```

The response includes metadata showing which model actually served the request and the fallback trail. That is how you verify the "switch when limit hit" behaviour: send requests until a free tier is throttled, then check the served model changes while your endpoint/URL stays the same.

### 2.5 Use it from the dbt lab (OpenCode V2 config)

The repo ships an `opencode.json` using the older `provider`/`npm`/`options` shape. **OpenCode V2 uses `providers`/`package`/`settings`** — use this version instead, in `~/.config/opencode/opencode.jsonc` (global) or `.opencode/opencode.jsonc` (project):

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "model": "freellmapi/auto",
  "providers": {
    "freellmapi": {
      "name": "FreeLLMAPI (local)",
      "env": ["FREELLMAPI_API_KEY"],
      "package": "@opencode/ai/providers/openai-compatible",
      "settings": {
        "baseURL": "http://127.0.0.1:3001/v1"
      },
      "models": {
        "auto": {
          "name": "FreeLLMAPI Auto Router",
          "limit": { "context": 1048576, "output": 65536 }
        }
      }
    }
  },
  "mcp": {
    "servers": {
      "dblab": {
        "type": "local",
        "command": [
          "uv", "run", "--directory", "/Users/meliliismail/Documents/mcp-dbt-lab",
          "python", "mcp_server/server.py"
        ],
        "cwd": "/Users/meliliismail/Documents/mcp-dbt-lab",
        "protocol": "auto",
        "environment": {
          "DBT_DUCKDB_PATH": "/Users/meliliismail/Documents/mcp-dbt-lab/duckdb/lab.duckdb"
        }
      }
    }
  }
}
```

Export the key **in the environment that starts OpenCode**:

```bash
echo 'export FREELLMAPI_API_KEY="freellmapi-..."' >> ~/.zshrc
# or just for this session: export FREELLMAPI_API_KEY="freellmapi-..."
```

Then in OpenCode: `/models` → select `freellmapi/auto`; `/mcps` → check `dblab` is connected; ask it to use the dblab tools.

> The repo also offers `npx freellmapi setup-opencode --url http://localhost:3001 --api-key <key>`. Run it with `--dry-run` first. It merges configs safely, but may emit the legacy shape; the V2 snippet above is the authoritative version.

### 2.6 Wire the same endpoint into the lab's Python smoke test

Add to the lab `.env` (already gitignored):

```env
FREELLMAPI_API_KEY=freellmapi-...
LLM_BASE_URL=http://localhost:3001/v1
LLM_MODEL=auto
```

Using `scripts/llm_smoke_test.py` from the main guide:

```bash
set -a; source .env; set +a
uv run python scripts/llm_smoke_test.py    # base_url/model come from .env
```

### 2.7 Security notes

- The repo states **personal experimentation only** — don't treat free tiers as a production SLA.
- Provider keys are AES-256-GCM encrypted locally; your apps only get the unified key.
- Keep the gateway bound to `127.0.0.1`. Only use `HOST_BIND=0.0.0.0` on a trusted LAN.
- Never commit `FREELLMAPI_API_KEY`, `.env`, or the encryption key. In GitHub Actions, store it as a repository secret if a job needs it.

✅ **Checkpoint:** one curl call returns `OK`, and switching models in the dashboard/rules does not require changing your app config.

---

## Part 3 — GitHub from zero: repo → branch → PR → merge → rules

### 3.1 Initialize Git and make the first commit

```bash
cd /Users/meliliismail/Documents/mcp-dbt-lab

git init -b main
git status                       # confirm .env, target/, duckdb/*.duckdb are NOT listed
git add .
git commit -m "chore: bootstrap dbt + duckdb + mcp lab"
```

If `git status` shows `.env` or `duckdb/lab.duckdb`, fix `.gitignore` **before** committing. Secrets must never enter history.

### 3.2 Create the remote repository

**With GitHub CLI (fastest):**

```bash
gh auth login                    # once
gh repo create mcp-dbt-lab --private --source=. --remote=origin --push
```

**Or on the website:** go to <https://github.com/new> → name `mcp-dbt-lab` → choose Private → **do not** add README/license (you already have files) → Create. Then:

```bash
git remote add origin git@github.com:<your-user>/mcp-dbt-lab.git
git push -u origin main
```

### 3.3 The branch → PR → merge cycle

```bash
# 1. Always start from an up-to-date main
git switch main
git pull

# 2. Create a focused branch
git switch -c feature/mcp-dev-testing

# 3. Do the work, then review what you changed
git status
git add -p                       # stage selectively
git commit -m "feat: add MCP inspector dev test notes"

# 4. Push the branch
git push -u origin feature/mcp-dev-testing

# 5. Open a pull request
gh pr create --fill --base main
```

In the browser (or with `gh pr view`) you will see:

- **Conversation** — description, comments, review approvals.
- **Checks** — the CI jobs from `ci.yml`. They must go green.
- **Files changed** — the diff reviewers inspect.
- **Merge box** — choose **Squash and merge** for a clean history.

After green CI and approval:

```bash
gh pr merge --squash --delete-branch
git switch main
git pull
```

**Why branches and PRs?** `main` stays deployable. Every change gets a isolated place to fail, an automated check, and a human review before it lands. CI checks run on the PR's merge commit, so you catch problems before they reach `main`.

### 3.4 Branch protection rules (Settings → Branches)

Classic path: **Repo → Settings → Branches → Add rule** for branch name pattern `main`. (Newer UI: **Rules → Rulesets → New ruleset**.) Enable:

| Rule | Why |
|---|---|
| Require a pull request before merging | No direct pushes to `main` |
| Require approvals (1) | Someone else reviews the change |
| Require status checks to pass | Pick `Format & static checks` and `dbt parse + unit/data tests` — the exact job names from `ci.yml` |
| Require branches to be up to date before merging | Prevents merging stale code that passed CI against an older `main` |
| Require conversation resolution | All review comments must be resolved |
| Block force pushes and branch deletion | Protects history |
| Include administrators (optional) | Rules apply to you too |

> The status-check names must match the `name:` fields in your workflow jobs. If you rename a job, update the rule.

### 3.5 Repository secrets (Settings → Secrets and variables → Actions)

This lab needs **no secrets** — DuckDB is a local file and everything is ephemeral in CI. If you add a job that calls FreeLLMAPI:

1. Settings → Secrets and variables → Actions → **New repository secret**.
2. Name: `FREELLMAPI_API_KEY`, value: your unified key.
3. Reference in YAML as `${{ secrets.FREELLMAPI_API_KEY }}` — never paste the literal value.
4. Prefer not to call a paid/external endpoint in PRs from forks; secrets are not exposed to forked PRs by design.

### 3.6 Reading the GitHub UI

- **Actions tab** → workflow runs. `push` and `pull_request` events each create a run.
- A run contains **jobs** (`lint`, `dbt`) that run in parallel; each job contains **steps**.
- `concurrency` in the YAML cancels an older run when you push again to the same branch.
- `workflow_dispatch` lets you press **Run workflow** manually from the Actions tab.

---

## Part 4 — CI/CD explained step by step

### 4.1 CI vs CD in one paragraph

**Continuous Integration (CI):** every push/PR automatically builds the project and runs tests, so broken code is rejected early. **Continuous Delivery/Deployment (CD):** after CI passes, automatically package and ship (deploy docs, publish a model, release an artifact). This lab implements **CI only**; a CD extension would be a `deploy` job gated on `main` with an environment approval.

### 4.2 The workflow file, line by line

```yaml
name: CI
on: [push, pull_request, workflow_dispatch]
```
- `name` — what appears in the Actions tab.
- `on` — the **events** that trigger the workflow. `push` fires on every branch; `pull_request` fires when a PR is opened/updated; `workflow_dispatch` adds a manual button.

```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```
- `group` groups runs per branch/ref. If you push twice quickly, the first run is cancelled — saves minutes.

```yaml
jobs:
  lint: ...
  dbt: ...
```
- Each job is a **separate virtual machine** (`runs-on: ubuntu-latest`). They run **in parallel** and report independent status checks.

Common steps in both jobs:

| Step | What it really does | Why |
|---|---|---|
| `actions/checkout@v4` | Clones your repo into the runner at `$GITHUB_WORKSPACE` | CI needs your source code |
| `astral-sh/setup-uv@v9` with `enable-cache: true` | Installs `uv` and caches downloaded packages | Fast, reproducible installs |
| `uv python install` | Installs the Python version from `.python-version` / `pyproject.toml` | Matches your local interpreter |
| `uv sync --frozen` | Installs **exactly** the versions in `uv.lock`, no re-resolution | Reproducibility: "works locally" means works in CI |

`lint` job:

| Step | What it catches |
|---|---|
| `uv run pre-commit run --all-files` | Whitespace, trailing newlines, invalid YAML/JSON, large files, private keys, ruff lint/format issues, and `dbt parse` errors via the local hook |

`dbt` job (job-level `env` sets `DBT_PROFILES_DIR` and an absolute `DBT_DUCKDB_PATH`):

| Step | What it proves |
|---|---|
| `uv run pytest -q` | Python seed-cleaning logic works on tiny fixtures |
| `uv run python scripts/process_seeds.py` | Raw CSVs load into DuckDB `raw` schema |
| `uv run dbt parse` | All YAML/Jinja compiles; DAG can be built — no database needed |
| `uv run dbt seed --select country_codes` | Lookup seed loads |
| `uv run dbt build` | Models materialize SA→INT→CA, then unit tests and data tests run in lineage order |
| `uv run dbt test --select test_type:unit` | Explicit unit-test gate, easy to spot in logs |
| `uv run dbt docs generate` | `manifest.json` + `catalog.json` are valid |
| `actions/upload-artifact@v4` with `if: always()` | `target/` is downloadable even if a previous step failed — essential for debugging |

### 4.3 Why the CI database is ephemeral

`DBT_DUCKDB_PATH: ${{ github.workspace }}/duckdb/ci.duckdb` creates a **fresh file per run**. Every run starts from the committed seeds only. That prevents "it passed because yesterday's data was still there" bugs.

### 4.4 How to debug a red build

1. Open the **Actions** tab → click the run → click the failing job.
2. Expand the failing step. dbt prints the compiled SQL path and failing row counts.
3. If the failure is a data test, download the `dbt-artifacts` ZIP and inspect `run_results.json`.
4. Reproduce locally with the same commands from the main guide's checklist.
5. Push a fix to the same branch — the PR's checks re-run automatically.

---

## Part 5 — pre-commit explained

### 5.1 What pre-commit is

`pre-commit` is a framework that installs small scripts into `.git/hooks/pre-commit`. From then on, **every `git commit`** runs those scripts before the commit is created. Hooks normally receive only **staged files**, which keeps them fast.

Two commands matter:

```bash
uv run pre-commit install          # once per clone; wires the git hook
uv run pre-commit run --all-files  # run against every tracked file, now
```

### 5.2 What happens on a normal commit

1. You `git add` files and type `git commit -m "..."`.
2. pre-commit runs each hook in order.
3. If a hook **modifies** a file (e.g. removes trailing whitespace), the commit is **aborted**. Re-stage (`git add .`) and commit again.
4. If all hooks pass, the commit is created.

This is deliberate: a failed hook is feedback, not an error to bypass. Avoid `--no-verify` unless you know exactly why.

### 5.3 Each hook in the config

```yaml
hooks:
  - id: trailing-whitespace      # strips spaces at line ends
  - id: end-of-file-fixer        # ensures exactly one newline at EOF
  - id: check-yaml               # YAML parses (catches broken CI/dbt YAML)
  - id: check-json               # JSON parses (catches broken MCP/OpenCode config)
  - id: check-added-large-files  # blocks accidental big files (e.g. a .duckdb)
  - id: detect-private-key       # blocks committed SSH/API private keys
  - id: ruff         (args: --fix)  # Python lint + auto-fix
  - id: ruff-format               # Python formatting
```

And the project-specific local hook:

```yaml
- repo: local
  hooks:
    - id: dbt-parse
      name: dbt parse (catch YAML/Jinja errors)
      entry: uv run dbt parse --quiet
      language: system             # use the already-installed uv/dbt, no new env
      pass_filenames: false        # dbt parse does not take file arguments
      files: ^(models|seeds|macros|tests|dbt_project\.yml|profiles\.yml)/
      env: [DBT_PROFILES_DIR=.]
```

- `files:` is a regex — the hook only runs when staged files match those paths.
- `pass_filenames: false` stops pre-commit from appending file paths to `dbt parse`.
- `env:` gives the hook the same profile setting you use locally.

### 5.4 Everyday commands

```bash
uv run pre-commit run --all-files              # check everything
uv run pre-commit run ruff --all-files         # only one hook
uv run pre-commit autoupdate                   # pin current hook versions
SKIP=dbt-parse git commit -m "..."             # skip one hook for a WIP commit
uv run pre-commit uninstall                    # remove the git hook
```

After `autoupdate`, re-run `--all-files` — new hook versions may reformat files. Commit those changes.

### 5.5 pre-commit vs CI

| | pre-commit | CI |
|---|---|---|
| Where | Your machine | GitHub runner |
| When | Before each commit | On every push / PR |
| Speed | Seconds | 1–3 minutes |
| Purpose | Fast feedback for you | Enforced truth for the team |

They should run **the same checks**. That is why CI calls `pre-commit run --all-files` instead of maintaining a separate list.

---

## 6. Do these in this order

```text
[ ] 1. uv add "mcp[cli]" ; copy mcp_server/server.py from main guide step 9.2
[ ] 2. uv run mcp dev -e . mcp_server/server.py → 4 tools, queries work
[ ] 3. Clone freellmapi into ~/freellmapi-src ; docker compose up -d
[ ] 4. Add provider keys + order Fallback Chain + copy unified key
[ ] 5. curl /v1/chat/completions with model "auto" → OK
[ ] 6. Add OpenCode V2 provider config + export FREELLMAPI_API_KEY
[ ] 7. git init -b main ; commit ; gh repo create ... --push
[ ] 8. Create feature branch, change something, push, gh pr create
[ ] 9. Watch CI jobs go green ; add branch protection with the two job names
[ ] 10. gh pr merge --squash --delete-branch ; pull main
```

✅ **You are done when** the Inspector lists your 4 tools, the FreeLLMAPI endpoint answers with a unified key, a PR shows two green checks, and `main` refuses direct pushes.

### Reference links

- MCP SDK CLI: <https://modelcontextprotocol.io/docs/develop/build-server>
- FreeLLMAPI repo: <https://github.com/tashfeenahmed/freellmapi> · docs: <https://freellmapi.co>
- OpenCode MCP: <https://opencode.ai/docs/mcp-servers> · providers: <https://opencode.ai/docs/providers>
- GitHub branch rules: <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches>
- GitHub Actions: <https://docs.github.com/en/actions>
- pre-commit: <https://pre-commit.com/>

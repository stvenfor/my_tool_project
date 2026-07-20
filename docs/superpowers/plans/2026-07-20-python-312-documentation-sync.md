# Python 3.12 Documentation and Feishu Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish an evidence-backed whole-repository Python 3.12 standardization guide locally and as a new Docx node in the Feishu wiki space `AI项目`.

**Architecture:** Keep `docs/python-3.12-standardization.md` as the reviewed source document and expose it from `docs/README.md`. Perform a one-time, idempotent Feishu sync by checking the exact wiki title, creating a new Docx node only when there is no match, writing the Markdown body through the returned `obj_token`, and fetching the result for verification.

**Tech Stack:** Markdown, Git, Python 3.12.13, npm/unittest verification, `lark-cli` 1.0.66, Feishu Wiki and Docx APIs.

## Global Constraints

- The local document title is `my_tool_project：Python 3.12 统一环境与迁移指南`.
- The target Feishu wiki space is the exact user-space match `AI项目`, space ID `7662216239732755696`.
- All Feishu Wiki and Docs calls use `--as user`.
- Do not modify, move, overwrite, or delete any existing Feishu node.
- Treat `docs/python-3.12-standardization.md` as the reviewed source of truth.
- The document must distinguish verified current state from unimplemented target state.
- Success requires local Git checks, Python 3.12 verification, 146 tracked Python files, ETF 142/142 tests, a successful Feishu write, and a successful Feishu read-back.

---

### Task 1: Finalize and commit the local guide

**Files:**
- Create: `docs/python-3.12-standardization.md`
- Modify: `docs/README.md`
- Create: `docs/superpowers/plans/2026-07-20-python-312-documentation-sync.md`

**Interfaces:**
- Consumes: the current repository, Python 3.12.13, existing module requirements and npm scripts.
- Produces: a committed Markdown source document that Task 2 sends to Feishu.

- [ ] **Step 1: Check the document for placeholders and malformed patches**

Run:

```bash
git diff --check
rg -n '(TBD|TODO|FIXME|待补|待定|尚未确认)' docs/python-3.12-standardization.md
```

Expected: `git diff --check` exits 0 and `rg` returns no matches.

- [ ] **Step 2: Reproduce the documented Python baseline**

Run:

```bash
python312_bin="$(pyenv root)/versions/3.12.13/bin/python3"
test -x "$python312_bin"
"$python312_bin" --version
test "$(git ls-files '*.py' | wc -l | tr -d ' ')" = 146
"$python312_bin" -m compileall -q modules
PATH="$(dirname "$python312_bin"):$PATH" npm run etf:test
```

Expected: Python reports `3.12.13`, the tracked-file assertion exits 0, compileall exits 0, and ETF reports `Ran 142 tests` followed by `OK`.

- [ ] **Step 3: Review the exact Git scope**

Run:

```bash
git status --short
git diff -- docs/README.md
```

Expected: only the new guide, this plan, and the single documentation-index line are in scope.

- [ ] **Step 4: Commit the documentation**

Run:

```bash
git add docs/python-3.12-standardization.md docs/README.md docs/superpowers/plans/2026-07-20-python-312-documentation-sync.md
git diff --cached --check
git commit -m "docs: add Python 3.12 standardization guide"
```

Expected: the staged diff check exits 0 and Git creates one documentation commit.

### Task 2: Create and verify the Feishu wiki document

**Files:**
- Read: `docs/python-3.12-standardization.md`

**Interfaces:**
- Consumes: the committed Markdown source from Task 1 and authenticated `lark-cli --as user` access.
- Produces: one new Docx node in Feishu wiki space `AI项目`, with the repository guide as its body.

- [ ] **Step 1: Verify identity, permissions, target space, and exact-title absence**

Run:

```bash
LARKSUITE_CLI_NO_UPDATE_NOTIFIER=1 LARKSUITE_CLI_NO_SKILLS_NOTIFIER=1 \
  lark-cli auth status --json --verify

LARKSUITE_CLI_NO_UPDATE_NOTIFIER=1 LARKSUITE_CLI_NO_SKILLS_NOTIFIER=1 \
  lark-cli wiki +node-list \
  --as user \
  --space-id 7662216239732755696 \
  --page-all \
  --page-limit 0 \
  --format json
```

Expected: user identity is `ready` and `verified`, the required Wiki/Docx scopes are present, and no node has the exact title `my_tool_project：Python 3.12 统一环境与迁移指南`. If an exact-title node already exists, stop without writing and ask the user whether to update that specific node.

- [ ] **Step 2: Preview the Wiki node creation**

Run:

```bash
LARKSUITE_CLI_NO_UPDATE_NOTIFIER=1 LARKSUITE_CLI_NO_SKILLS_NOTIFIER=1 \
  lark-cli wiki +node-create \
  --as user \
  --space-id 7662216239732755696 \
  --obj-type docx \
  --title 'my_tool_project：Python 3.12 统一环境与迁移指南' \
  --dry-run \
  --format json
```

Expected: the preview targets space ID `7662216239732755696`, object type `docx`, and the exact title; no resource is created.

- [ ] **Step 3: Create exactly one new Wiki Docx node**

Run:

```bash
FEISHU_CREATE_JSON="$(
  LARKSUITE_CLI_NO_UPDATE_NOTIFIER=1 LARKSUITE_CLI_NO_SKILLS_NOTIFIER=1 \
    lark-cli wiki +node-create \
    --as user \
    --space-id 7662216239732755696 \
    --obj-type docx \
    --title 'my_tool_project：Python 3.12 统一环境与迁移指南' \
    --format json
)"
printf '%s\n' "$FEISHU_CREATE_JSON"
FEISHU_DOC_TOKEN="$(printf '%s\n' "$FEISHU_CREATE_JSON" | jq -r '.data.obj_token // empty')"
FEISHU_NODE_TOKEN="$(printf '%s\n' "$FEISHU_CREATE_JSON" | jq -r '.data.node_token // empty')"
test -n "$FEISHU_DOC_TOKEN" && test -n "$FEISHU_NODE_TOKEN"
```

Expected: one node is created in `AI项目`; the returned `obj_type` is `docx`. Do not retry creation after an ambiguous network response—list exact-title nodes first.

- [ ] **Step 4: Write the reviewed Markdown body**

From the repository root, stream the document without its first H1 line so the Wiki node title is not visually duplicated:

```bash
sed '1d' docs/python-3.12-standardization.md | \
  LARKSUITE_CLI_NO_UPDATE_NOTIFIER=1 LARKSUITE_CLI_NO_SKILLS_NOTIFIER=1 \
  lark-cli docs +update \
  --as user \
  --doc "$FEISHU_DOC_TOKEN" \
  --command overwrite \
  --doc-format markdown \
  --content - \
  --format json
```

Expected: the response has `ok: true`, `result: success`, a positive updated-block count, and no failed warning. This overwrite is allowed only on the newly created empty document from Step 3.

- [ ] **Step 5: Read back and validate the Feishu document**

Run:

```bash
LARKSUITE_CLI_NO_UPDATE_NOTIFIER=1 LARKSUITE_CLI_NO_SKILLS_NOTIFIER=1 \
  lark-cli docs +fetch \
  --as user \
  --doc "$FEISHU_DOC_TOKEN" \
  --doc-format markdown \
  --detail simple \
  --format json
```

Expected: `ok: true`; the title is exact; the body contains `## 1. 结论`, `## 5. 模块风险分层`, `## 10. 验收标准`, and `## 12. 回滚方案`; the returned revision is newer than the empty document revision.

- [ ] **Step 6: Confirm local repository cleanliness**

Run:

```bash
git status --short --branch
git log -2 --oneline --decorate
```

Expected: the working tree is clean and the documentation commit is at `HEAD`. The Feishu write does not create additional local files.

# Security

This document covers how secrets are handled in this repository, how to rotate
the LLM provider credentials, and what to do if a key is ever exposed.

## Where secrets live

Secrets are **never** stored in the source code. They are read from the
environment by `config.py` (via `python-dotenv`), using the local `.env` file:

```env
GOOGLE_API_KEY=...
NVIDIA_NIM_API_KEY=...
CEREBRAS_API_KEY=...
```

`.env` is gitignored, and so is every variant of it (`.env.production`,
`.env.dev`, ...). Only `.env.example` — a template full of
`your_*_here` placeholders — is tracked.

| File | Contains real secrets? |
|------|------------------------|
| `.env` | Yes — gitignored, never committed |
| `.env.example` | No — placeholders only |
| `config.py` | No — reads from the environment |
| `scripts/check_secrets.py` | No — detection rules only |

## Guard rails

Two layers protect the repository from an accidental secret commit:

1. **Pre-commit hook** — scans the staged files on every commit.
2. **CI** — runs the same scanner over the tracked files and the full history
   on every push and pull request.

Enable the local hook once per clone:

```bash
git config core.hooksPath .githooks
```

Manual usage:

```bash
python scripts/check_secrets.py           # staged files
python scripts/check_secrets.py --all     # every tracked file
python scripts/check_secrets.py --history # every blob in every commit
```

Findings are redacted: the scanner prints the file, the line and the kind of
credential, never the credential itself.

> **Note:** the scanner is a safety net, not a guarantee. It matches known
> credential formats and high-entropy assignments. A secret pasted inside a
> string, a base64 blob or a novel format can still slip through — keep using
> `.env` and treat the hook as a backstop, not as the primary control.

## Rotating the LLM provider keys

The framework supports three providers (see `llm_provider.py`):

| Provider | Environment variable | Where the key is created |
|----------|----------------------|--------------------------|
| NVIDIA NIM | `NVIDIA_NIM_API_KEY` | <https://build.nvidia.com/> |
| Cerebras | `CEREBRAS_API_KEY` | <https://cloud.cerebras.ai/> |
| Google Gemini | `GOOGLE_API_KEY` | <https://aistudio.google.com/apikey> |

### Why rotate

Keys should be rotated on a regular schedule, and **immediately** whenever
there is any suspicion of exposure. In particular, a key is considered
exposed if it was:

- ever committed, even if the commit was later removed (the blob stays in the
  history and can be pulled from the remote);
- pasted in a chat, a ticket, a screenshot or a CI log;
- stored on a shared or compromised machine.

Rotating means **creating a new key at the provider and revoking the old
one** — not just editing the local file. A key that was once exposed stays
valid at the provider until it is explicitly revoked there.

### Procedure

For each provider you actually use:

1. **Create a new key** in the provider dashboard.
2. **Update `.env`** with the new value (leave the old one in place for now).
3. **Verify it works** — run one job in debug mode and confirm the vision
   click loop still resolves targets:
   ```bash
   python job_runner.py --job-id <a-real-job-id> --debug
   ```
   Or check the provider directly with a single call.
4. **Revoke the old key** in the provider dashboard.
5. **Update your other installations** — the key may be in use on a VPS, in a
   container, in a CI secret store or in a local `.env` elsewhere. A rotation
   that only touches one machine leaves the old key alive elsewhere.
6. **Confirm the old key is dead** — a request using it must fail.

### After rotating

The local `.env` is gitignored, so a rotation never touches the repository.
No commit is required. If the old key was ever committed, rotation alone is
not enough: the history still contains it, so also follow the next section.

## If a key is found in the git history

1. **Rotate the key first.** The history is public; assume it was read.
2. **Purge the blob.** Use `git filter-repo` (preferred) or BFG to rewrite the
   history and remove the secret from every commit:
   ```bash
   pip install git-filter-repo
   git filter-repo --path <file-with-the-secret> --invert-paths
   # or, to replace the value everywhere:
   git filter-repo --replace-text expressions.txt
   ```
3. **Force-push the rewritten history** to every remote and every branch:
   ```bash
   git push --force --mirror origin
   ```
4. **Tell everyone who cloned the repo** to re-clone or reset to the rewritten
   history — their local copies still contain the secret.
5. **Check the CI logs and the provider dashboards** for signs of abuse.
   Provider dashboards usually show the requests made with a key, which tells
   you whether the key was actually used by someone else.

> Rewriting history is disruptive: every other clone becomes divergent and
> open pull requests have to be recreated. It is still the right call for a
> live credential in a public repository.

## Reporting a vulnerability

If you find a security problem in this repository, please report it privately
to the maintainer instead of opening a public issue.

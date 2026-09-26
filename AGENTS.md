# Development guidance

This repository is an independent DeepSeek Harness plugin. Read [README.md](README.md) and the [package reference](packages/jev/README.md) before changing public behavior.

- Implement features through documented DSH extension points; do not patch DSH, Mu, or Cua as part of this project.
- Keep unrelated worktree changes intact. Stage explicit paths, not the entire checkout.
- Never commit credentials, local profiles, raw user-session captures, personal screenshots, or generated runtime artifacts.
- Keep English and Chinese README instructions and feature status aligned. Distinguish main from unmerged and paused branches.
- Run checks appropriate to the changed surface. Real model calls, changes to user profiles, and publishing require explicit authorization.
- Every registration owns a disposer. Model-visible effects use DSH Session records; auxiliary Jev decisions use the plugin ledger.
- Build and test from an isolated feature worktree. Local planning records under .agents/notes remain private and do not ship in the package.

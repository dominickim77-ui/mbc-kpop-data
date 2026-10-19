# STEP 18 — Approved Video ID Lock

Goal: prevent a newly selected YouTube candidate from replacing the current latest *manually approved* Video ID. Backend returns HTTP 409 even if frontend is bypassed. Existing verified historical approvals are read-only, and approvals remain editorially separate from weekly YouTube Top Songs data.

Run from `C:\WORKSPACE\mbc-kpop-data` on `feature/kpop-news-analysis`, with server stopped:

```powershell
python kpop_step18_patch\install_step18.py --dry-run
python kpop_step18_patch\install_step18.py
python kpop_step18_patch\verify_step18.py
```

Then start Uvicorn and inspect the existing KATSEYE Animal candidates. It should show a lock for `m7k9UMcHbr0`, with approval button disabled. Existing review JSON and DB histories are never edited by installation.

**Limit:** This is a local single-process lock. It does not independently authenticate an official YouTube channel, and it is not a correction/revocation workflow. To replace an existing approval legitimately, design a separate, explicit correction workflow with an audit trail. Do not remove JSON files or update MySQL manually.

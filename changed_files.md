# 1177.pdhc — Changed Files Log

All edited files with full paths, per Rule 17.

- 2026-04-16: safe_restart.sh — ticket #78 (#75 reconcile, 1177 service): merged local+server divergent versions. Server had `export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` (gunicorn fork-safety fix matching pdhc-wide memory); local had superior logging (error/access logfiles to `logs/`) + 5-retry health check with tail-on-failure. Kept local version as base + added fork-safety export near top. Deployed to server (sha f9353d12...). Not restarted — script-only change, picked up on next graceful restart.
- 2026-04-16: app/routes/health.py — ticket #70 adds Access-Control-Allow-Origin https://www.pdhc.se + Methods GET + Vary: Origin + Cache-Control: no-store on /api/health so services.html can use mode:'cors' instead of no-cors false-greens.
- 2026-04-16: NOT SYNCED (ticket #78 pending operator decision): server has `app/routes/inbound.py` (PDHC push receiver from request.pdhc, 44 lines) that is ORPHANED — the server's `app/__init__.py` does not register `inbound_bp` (verified: `grep inbound /usr/local/www/1177.pdhc/app/__init__.py` → no match; __init__.py shas are identical across local and server). So the file exists on disk but receives no traffic. Decision needed: wire it up or delete. And `pdhc_keyauth/` 11-file shared-module subtree exists on server only — structural-decision, likely a shared module that should live elsewhere.

| 2026-07-13 | docs/user_manual.md, docs/technical.md (new) | Authored user manual + technical spec (no docs existed); published on www.pdhc.se/documentation.html. |
- 1177.pdhc/docs/technical.md (Port Allocation section)
- tests/conftest.py, tests/test_models.py, tests/test_routes.py — drop removed app.models.user.User; rewrite login fixture+tests for pdhc_keyauth (suite 51 passed, was 20p/1f/22err)

- app/routes/health.py — canonicalise /api/health to §10 shape (add `service`, degraded→503, `unavailable` wording). Deployed 2026-08-14 (forms_1177_app rebuild).

#941 — pdhc_keyauth is version-controlled at last (2026-11-05)
--------------------------------------------------------------
NO FILE IN THIS REPO CHANGED. Recorded here because this service's auth comes
from a directory outside it.

`1177.pdhc/pdhc_keyauth` is a symlink to `~/T7_sidewinder/pdhc_keyauth`, which held
680 lines of Flask auth code under NO version control from 2026-04-05 until
now — tracked by no repo, invisible to `git status`. It is a git repo of its
own as of 355016e, with a README carrying the measurements.

Nothing changed at runtime: same inode, symlink untouched, and this suite is
green afterwards. No production change either — the one unreleased fix in
there (#563's idempotent `define_models`) is test-only, because a deployed
process calls `create_app()` once per gunicorn worker.

Worth knowing about this service specifically: on miserver the three consumers
have THREE INDEPENDENT real directories, not symlinks, all holding the
pre-#563 copy. So a fix made on the Mac does not propagate to production here,
and a fix made in production to one service does not reach the other two.

Open: whether to consume it as a submodule or a package. This line used to say
"#943 holds that decision, since it is the same question as the 14 modules
copied across repos". #943 was CLOSED 2026-11-06 with its premise disproved —
session_headers.py has ONE code variant across seven repos, not four; the
largest duplicate group was Flask-Migrate's generated migrations/env.py in 14
repos; and the copies are a documented deliberate choice. cgm/provider turned
out to be a ratified FORK (#946), not copied modules. So pdhc_keyauth is now
the ONLY live instance of this question. See CLAUDE.md §4.

2026-11-06: pdhc_keyauth now has a PRIVATE remote,
github.com/profingvar/pdhc_keyauth, so this service's auth code is backed up
off this machine for the first time. The symlink is untouched.

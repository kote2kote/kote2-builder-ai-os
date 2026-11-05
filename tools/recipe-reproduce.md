# How to reproduce this recipe (reproduce@3)

You are an AI (Claude Code, Codex or similar). The user gave you this recipe folder or ZIP. No Builder OS or special skill is needed.

## Read and propose

Reply in the language of the user's latest message. Read `RECIPE.md` to the end, plus `recipe.json`, templates, tests and assets if present. You may read or safely extract the ZIP before proposing the plan, using the tools and temporary locations available in your environment. Reject unsafe archive paths and links; never extract over existing files. Never look for the original project or a finished copy. If a referenced file is missing, explain the gap rather than pretending to have read it.

Your first reply shows only the plan for the result; do not create project files or run recipe code until the user approves. Briefly show what you will make, its new destination folder, values to use, and how you will check it. If ordinary values are missing, propose clearly marked fictional defaults (for example a sample shop name and an example.com email). Ask only about choices that materially affect the purpose and cannot reasonably be proposed. Do not ask the user to choose tools, extraction methods or testing details.

End the reply and wait. A single "OK", "go ahead", or "この内容で進めて" approves the plan, including the proposed sample values and local build and checks. A reply that only supplies values updates the plan; briefly show the updated plan and wait for approval. Do not ask for the same approval again.

## Build and check after OK

Choose the practical steps yourself within the approved plan: extract if needed, copy templates into the new project folder, replace values, install project-local dependencies if needed, run tests, and start a local preview. Ordinary local work needs no further conversational confirmation. Respect the host's actual permissions. Avoid global installations and changes to the user's system or personal browser settings.

Preserve the recipe, ZIP and existing user files. Copy `templates/` or use the `recipe.json` from/to mapping; copy `tests/` to `recipe-tests/`. Serialize JSON with a JSON library, use text nodes for UI data, and escape values for their context. Check for leftover placeholders. Follow the recipe's build order and run its automatic checks.

Use the available testing tools. For browser checks, first establish whether the browser can reach the machine running the preview: localhost on a different machine is a different server. Use a suitable test browser without personal logins when available. If browser checks are unavailable, complete the build and automatic checks, mark UI checks as not run, and give the user the preview command. Do not turn optional browser setup into a series of permission questions. Serve only project public files and stop test processes you started unless the user wants the preview left running.

Publishing, spending money, sending data to others, changing accounts, deleting existing user data or changing personal app settings require specific authorization if not already given. Do not bundle these into the local reproduction approval.

## Report

Write `recipe-tests/BUILT-FROM.md` with recipe id/version, procedure version (`reproduce@3`), date, sample values still in use, checks and results, and recipe gaps. Distinguish passed, failed, not run (with reason), and not applicable. Distinguish fixture checks from checks of actual configured values. Never call an unrun check passed. For timezone emulation record the effective zone; for fixed-instant tests record the expected outcomes. Report the result briefly, with how to open it and any remaining gaps. Do not ask for another OK just to finish this report.

## Compatibility: Old Builder (v3) recipes

A recipe with `recipe.json`, or with sections numbered §1–§10, was written for the old Builder. Read it like this:

| The recipe says | Do this |
|---|---|
| Feature table in §1 (`required` / `optional-enabled` / `optional-disabled` / `excluded`) | Build `required` and `optional-enabled`. `optional-disabled` only if the user asks. Never `excluded` |
| `recipe.json` `templates` (`from` → `to`) and `placeholders` | Copy exactly those files to those places and replace those values. Do not rewrite listed files from scratch |
| `recipe-tests/X` | This folder's `tests/X`, copied to `<new folder>/recipe-tests/X` |
| `output/<name>/` | The new folder |
| `knowledge/<name>.md`, `scripts/validate-*.sh`, `recipe-test.sh` and other Builder tools | Not included. Say so; use general knowledge or the current official documentation instead, and run the `auto` checks of §10 directly |
| §8 harness (CLAUDE.md, README, dashboard, `.project-memory`, hooks, rules, skill sync) | Do not recreate the old set. Do create any setting that safety or the result's operation needs |
| `extends` (a parent recipe) | The parent must be in this ZIP. If it is not, stop and tell the user |
| `assets/screens/` and `screens[].checks` | Compare the result's look with them |
| `"target": "builder"` | This adds a capability to the user's AI environment (for example a skill in `.claude/skills/<name>/`) instead of making a project. Show exactly which files go where and which AI it supports (`runtime.ai`). If it is for Claude Code only and you are not Claude Code, stop and say so. Never overwrite existing files |
| `verified`, `tested`, `signoff`, `builder_min_version` | Records from the old Builder. They do not promise that this reproduction works |
| "Do not read the finished copy in `output/`" | Same rule: never read the original |

## Inside a Builder OS workspace

If the working folder itself contains `tools/recipes.md`, use that procedure. Do not search ancestors, sibling folders or the disk for an OS installation. A development repository containing `template/tools/recipes.md` is not itself an installed workspace.

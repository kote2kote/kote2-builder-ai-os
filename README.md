# kote2 Builder AI OS

**A workspace for thinking with AI, building things, and putting experience to work on your next project.**

Keep conversations and decisions from Claude Code or Codex in a **Wiki**, your deliverables in **projects**, and reusable ways of working in **recipes**. Pick up where you left off on another day—or with another AI—by referring to those records. This is a working environment, not a replacement for your computer's operating system.

## What you can do

- **Think together** — Explore ideas with the context of your work and past records.
- **Build** — Review a design for an app, document, or workflow, then approve it before implementation and verification.
- **Reuse what you learn** — Keep decisions and experience in the Wiki, and reusable methods in recipes.

Try asking, “Look through the Wiki and suggest things we could turn into recipes or skills.” The AI considers the source records, outcomes, and missing information. Choose a candidate before drafting it, then test it under different conditions. Installing or publishing a skill requires a separate confirmation. [Turn experience into reusable capabilities](tools/experience.md) (Japanese).

## What you need

- **Claude Code or Codex** — The AI you use to work in this folder.
- **Git** — Keeps a history of your records so you can return to an earlier state.
- **GitHub CLI (`gh`)** — Checks the official GitHub source and commit when updating the OS. Use official versions of Git and `gh` that you have verified as trustworthy.
- **Python 3.11 or later is recommended for all features** — Runs the included Wiki, import, and update tools. Python 3.11 or later is **required for Codex configuration checks** in `tools/building_check.py`, which use `tomllib`.

Tested on macOS. Final verification on Windows is not complete. Your chosen AI environment requires its own access plan and configuration. Check the distribution version in [VERSION](VERSION).

**Language:** This README is in English. Most included guides, templates, and tool messages are currently in Japanese. The AI instructions ask it to respond in your language; this is not a fully English-localized distribution.

## Getting started

1. **Verify the official distribution.** Have a person check the URL, numeric repository ID, pinned commit, and contents of the official repository, `kote2kote/kote2-builder-ai-os`. Create your own **private** repository with “Use this template,” or copy only the files from a clone used for verification into a separate folder and run an independent `git init`. Do not bring the official repository's `.git` directory into your workspace, or delete or replace an existing user's `.git` directory. Stop if you cannot verify the source. [Detailed setup guide](tools/setup.md) (Japanese).
2. **Open the whole folder with your AI.** In Claude Code or Codex, open the folder containing this README—not a subfolder such as `wiki/`.
3. **Say what you want to do.** Start in everyday language: “Hello” or “I'd like to create a document.”

Check the settings your AI actually loaded from the workspace or project root. Preserve existing custom settings. Claude's file rules and Codex's sandbox have different scopes; a project configuration does not provide complete isolation of secrets. See [AI settings and limits](tools/building/settings.md) (Japanese).

Claude Code's shared settings do not require a sandbox, so they can also be used on native Windows. They retain secret-file Read/Edit denies, dangerous Git denies, and ask rules for push/publish. Without a sandbox, these rules do not guarantee that Bash or other indirect access paths cannot reach secrets. On macOS, Linux, or WSL2, users can opt in using the [sandbox settings example](tools/building/templates/claude-sandbox-settings.json) and the [local setup instructions](tools/building/settings.md). Preserve custom settings; do not replace an existing settings file with the example.

You can choose an optional seven-topic onboarding interview to introduce yourself, or skip it and get straight to work. You do not need to register a profile.

For any topic, ask, “Interview me about…” or “Please start interview mode.” The AI asks one question at a time to help clarify your work, concerns, ideas, or requirements. It records key answers, organizes confirmed points at a stopping point, and uses relevant Wiki records in later conversations. You can pause or stop; ending an interview does not authorize building or external actions. [Interview guide](tools/interview.md) (Japanese).

## Things you can ask

The Wiki sidebar includes an **OS feature guide** and a **skills list**. Each skill shows its AI-specific invocation and a natural-language request you can copy. The list refreshes when opened, reloaded, or revisited; it does not execute or install skills. It discovers direct workspace and personal skill locations, not every plugin or nested project. [Feature guide](tools/features.md) (Japanese).

| Goal | Example request |
|---|---|
| Discuss or create something | “I'd like to discuss…” / “I'd like to build…” |
| Resume work | “Please continue where we left off yesterday.” |
| View or edit records | “Show me the Wiki.” / “Update this record.” |
| Use or save a method | “Show me the recipes.” / “Turn this into a recipe.” |
| Save or restore history | “Please save my work.” / “I'd like to return to an earlier state.” |
| Match a visual style | “Match the design of this document.” |
| Explain with a diagram or video | “Make a diagram of how this project works.” / “Make an explainer video about this.” (video: Claude Code only) |
| Try before building | After the design, “Make a prototype I can try first.” |
| Start from a prototype | Attach a ZIP and ask, “Could we build an app like this?” |
| Continue an existing project | “Can you manage this existing project here?” Share its folder location; the AI checks it and proposes a connection plan before changing anything. |
| Update the OS | “Please update the OS.” |

For new work or major changes, the AI shows a design first. It also asks before publishing, sending anything externally, or taking actions that incur costs.

Projects made outside Builder can also be connected for ongoing work. Keep the original location, or approve a copy into `projects/`. The AI checks existing instructions, settings, and history first; copying a folder alone does not configure it or prove that it runs. Existing files are not replaced with new-project templates. See [existing projects](tools/building/existing-projects.md) for the procedure.

## Folder structure

The three folders you will use most are **`wiki/`, `projects/`, and `recipes/`**. You do not need to read every configuration file before starting.

```text
workspace/
├── README.md          ← Start here (this page)
├── wiki/              ← Records about you and your work
│   ├── index.md       ← Contents and work in progress
│   ├── me/            ← Profile, preferences, and requests for the AI
│   ├── projects/      ← Project index, context, and decisions
│   └── notes/         ← Topic guides, research, and knowledge
├── projects/          ← Deliverables: apps, documents, and more
├── recipes/           ← Reusable methods and included recipes
├── tools/             ← Tools and guides for the Wiki, migration, and updates
├── DESIGN.md          ← Default design system
├── AGENTS.md          ← Shared instructions for the AI
├── CLAUDE.md          ← Entry point for Claude Code
└── VERSION            ← Distribution version
```

`wiki/projects/` holds project **records**; the root `projects/` folder holds **deliverables**. Records are human-readable text files. Ask the AI to edit them in plain language.

## Explore your Wiki in 3D

See how your notes and projects connect. Explore the 3D graph and replay how your Wiki has grown over time.

![Animated demonstration of connected pages growing in kote2's Wiki graph](https://github.com/user-attachments/assets/dfb41563-1fea-4ac0-9303-cc9cd7579a7d)

*A demo using kote2's own Wiki. The interface shown is in Japanese.*

## Read when you need it

The linked guides below are currently in Japanese.

- **Using and editing the Wiki** → [Wiki guide](wiki/README.md).
- **Included recipes and how to use them** → [Recipe index](recipes/README.md).
- **Migrating from v3** → Tell the AI, “I'd like to migrate from v3.” It leaves the original v3 unchanged and confirms what to migrate. Deliverable source code is not copied automatically. [Migration details](tools/v3-migration.md).
- **Updating, undoing, or recovering the OS** → [Detailed guide](tools/os-update.md). You can also ask, “Is there an OS update?” The AI checks only the official GitHub VERSION first and tells you whether an update is available. If one is available, it investigates the contents in the same turn, explains how to preserve your customizations, the impact, and unresolved issues, then stops to ask whether you want to update. Your initial update request is not approval to apply it. After your OK, you approve the confirmation window yourself. Records, deliverables, recipes, and legal documents are not automatically synchronized.

## Use safely

- Do not put passwords, API keys, or other people's personal information in conversations or the Wiki.
- Keep work records private and maintain a separate backup. If you use GitHub, make your repository **private**.
- Information you share with an AI is handled under that AI service's terms. Check important deliverables yourself.
- The Wiki's 3D view and visual editor load code and other resources from external services, which receive information such as your IP address. Page browsing and the 2D view are available offline.

## Reporting problems

Report your version, environment, and reproduction steps in the official repository's [Issues](https://github.com/kote2kote/kote2-builder-ai-os/issues). Do not include personal information, secrets, or work records. External pull requests are not accepted. [Reporting guide](CONTRIBUTING.md) (Japanese).

## Release notes

- **4.5.1** — The first public release after 4.4.0. It adds the Wiki feature and skill guide, the unified "hearing mode" name ("interview" is accepted as an alias), and Windows migration fixes: the confirmation window's PowerShell runs in its own temporary folder and is cleaned up, diagnostics list every reason, and the corrected 4.3.2 transition bridge is supported.
- **About 4.5.0** — The number 4.5.0 was used only for a pre-release candidate installed in a limited number of local workspaces. It was never published on GitHub. Because that candidate and the final package differ, the published version is 4.5.1, not a second 4.5.0. A workspace on that 4.5.0 updates to 4.5.1 through the normal update; do not reinstall or re-apply 4.5.0.
- **Upgrade paths** — Skipped versions are fine: every published version from 4.3.1 on updates directly to the latest in one step (checked before each release). 4.4.0 → 4.5.1 directly. Pre-release 4.5.0 → 4.5.1. 4.0.0–4.3.0 need one transition release first, then go straight to the latest: native Windows → 4.3.2 → latest; other platforms → 4.3.1 → latest. 4.4.0 is no longer an intermediate stage. Each stage needs its own review and confirmation.

## License

The core is licensed under the [Apache License 2.0](LICENSE). Also review the [attribution notices](NOTICE) and [third-party terms](THIRD_PARTY.md).

The Himawari cat images are **not** covered by the Apache License 2.0. You may use them in explainer videos, publish and commercially use those videos, and redistribute the images as part of the complete OS package. Redistributing or selling the images on their own, or selling merchandise featuring the character alone, is prohibited. [Image usage terms](.claude/skills/explainer-video/character/TERMS.md) (Japanese).

kote2 does not claim rights to the deliverables you create with this OS. Check the terms of any materials and external services you use separately. This is not an official Anthropic or OpenAI product, is not affiliated with either company, and does not guarantee operation or results.

## For AI assistants

At the start of a new conversation, or when resuming a long one, automatically check only the OS version if at least 24 hours have passed since the previous check. Briefly notify the user of a newer version only once. Do not automatically download or apply it. See [how to disable or resume checks and the detailed conditions](tools/os-update.md#利用時の自動確認) (Japanese).

Use [AGENTS.md](AGENTS.md) for everyday work and [updates, undo, and recovery](tools/os-update.md) for OS updates and notification settings. For first-time setup checks, follow the [setup guide](tools/setup.md); do not skip verification. These guides are currently in Japanese.

### 4.3.0 and older (4.0.0–4.3.0) upgrades

The tools installed in these versions cannot read the current layout, and their bundled guides do not know the transition release, so "update the OS" alone stops at the first fetch. Paste one of these sentences to your AI instead (they are Japanese, like the guides):

- macOS and others: 「OSを最新版に更新して。4.3.0以前なので、公式READMEの手順どおり移行準備版4.3.1（`fd8aa58cfdb8de30b210f626521605c3a07af91a`）を経由して、同じ依頼のまま最新まで進めて」
- Native Windows: 「OSを最新版に更新して。Windowsの4.3.0以前なので、公式READMEの手順どおり移行版4.3.2（`e1474089163b40c4cd3b0ea93d27ccd717b2746f`）を経由して、同じ依頼のまま最新まで進めて」

**Other platforms (macOS and others):** Native skill paths require the **4.3.1 transition release first, then the latest**. The immutable transition commit in this public repository is `fd8aa58cfdb8de30b210f626521605c3a07af91a`. From your workspace, use its installed, trusted tool: `python3 -I tools/release_package.py fetch --ref fd8aa58cfdb8de30b210f626521605c3a07af91a --ws .`. Review the returned package and plan, preserve customizations, and approve the normal update confirmation before applying. After installing 4.3.1, continue the same request without asking the user to repeat it: check the official version again with the newly installed tools and fetch the resolved full commit of the latest version. 4.4.0 is not an intermediate stage. Each stage requires its own review, OK and confirmation, because the next stage's differences can only be checked after the previous stage is installed. If the transition commit cannot be fetched, stop; do not bypass the old verifier or execute candidate code before installation. See [the procedure](tools/os-update.md#430以前から公式配置版への移行) (Japanese).

**Using 4.3.0 or older (4.0.0–4.3.0) on native Windows?** Do not install the old 4.3.1 bridge, which requires an unsupported sandbox. Use the corrected **4.3.2 transition bridge** (full commit `e1474089163b40c4cd3b0ea93d27ccd717b2746f` on the `transition/4.3.2-windows` branch), then go straight to the latest. Follow [Windows migration and stop conditions](tools/windows-upgrade.md), verify the full public commit and external inventory receipt at each stage, and use only installed trusted fetch/check tools. Preserve custom settings and conflicting skills; obtain human confirmation at every stage. Never run candidate updater code before installation or automatically approve a confirmation.

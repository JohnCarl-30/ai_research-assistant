# Publishing Scout

Two steps need the maintainer's own accounts, so they are prepared here rather
than automated: signing the Claude Desktop bundle, and listing the plugin in
Anthropic's directory.

## Sign the Claude Desktop bundle

Claude Desktop shows a signed `.mcpb` as coming from a verified publisher. The
release workflow signs the bundle when a certificate is configured and ships it
unsigned otherwise.

1. Get a code-signing certificate from a certificate authority. A self-signed
   certificate is not enough: `mcpb verify`, like Claude Desktop, only trusts
   certificates that chain to a root in the operating system's trust store, and
   reports anything else as unsigned.
2. In the repository's **Settings → Secrets and variables → Actions**, add:
   - `MCPB_SIGNING_CERT`: the certificate, PEM text
   - `MCPB_SIGNING_KEY`: its private key, PEM text, unencrypted
   - `MCPB_SIGNING_CHAIN` (if your CA uses intermediates): the intermediate
     certificates, PEM text
3. Run **Release extension** by hand on `main` without **publish** ticked. The
   **Sign the bundle** step signs and then verifies the bundle, and the run
   fails if the signature doesn't verify, so a broken certificate never ships.

The key is written to a temporary file only for the signing step and deleted
when the step ends.

To sign a bundle by hand instead:

```bash
npx @anthropic-ai/mcpb@2.1.2 sign --cert cert.pem --key key.pem scout-X.Y.Z.mcpb
npx @anthropic-ai/mcpb@2.1.2 verify scout-X.Y.Z.mcpb
```

## List the plugin in Anthropic's directory

The directory no longer accepts `.mcpb` desktop extensions. A local MCP server
is listed inside a plugin, so the listing is for the **Claude Code plugin** in
`extension/`. Once listed, people can add it from claude.ai and use it in chat,
Cowork and Claude Code. The `.mcpb` stays on the Releases page for Claude
Desktop.

You need a paid Claude plan with permission to submit, and your GitHub account
connected on claude.ai with push access to this repository.

1. Open the developer portal at <https://claude.ai/directory/manage>, select
   **Submit new**, then **Plugin bundle**.
2. **Source:** the repository (`<owner>/ai_research-assistant`), plugin path
   `extension`, and branch `main` (or a release tag). Select **Validate** and
   fix anything marked **Blocking**.
3. **Data handling:** the facts to answer from: Scout stores notes, research
   snapshots, the watchlist and a response cache only on the user's computer,
   keeps them until the user deletes them, and sends only company names and
   domains (plus the optional GitHub token, to GitHub) to the public sources
   listed under **Privacy** in `extension/README.md`. Whether it is intended for
   people under 18 is your call.
4. **Compliance:** check the contact email and accept the acknowledgements.
5. **Review and submit:** keep **GitHub push webhook** so new versions are picked
   up on merge, then **Submit for review**.

Expect these findings, which a reviewer clears rather than you fixing:

- **Runs a pinned npx or uvx package**: the server starts with
  `uv run --locked`, so its dependencies come from PyPI at install time, at the
  versions in `extension/uv.lock`.
- **Scripts the validator couldn't follow**: the plugin is a subfolder of this
  repository and its server is Python, which the validator doesn't trace.

Already handled, and kept that way by `extension/tests/test_packaging.py` and CI:

- `uv run --locked`: the directory blocks `uv run` without it, and CI checks
  that `uv.lock` is current.
- No credentials from the user's environment: the optional GitHub token is a
  sensitive install setting, and Scout never reads `GITHUB_TOKEN`.
- A README of more than 40 words and a LICENSE in the plugin folder; no binary
  files, and every file under 256 KiB.
- Everything Scout fetches is listed in the README's **Privacy** section, as the
  security scan expects.

After the listing is live, every merge to the tracked branch is a new version:
raise the version with `scripts/bump_extension_version.py` for each release.

The current rules are in Anthropic's
[plugin pre-submission checklist](https://claude.com/docs/plugins/pre-submission-checklist)
and [Submit your plugin](https://claude.com/docs/plugins/submit).

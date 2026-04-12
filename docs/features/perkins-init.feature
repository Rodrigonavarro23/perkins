@constraints
# governed_by:
#   - docs/tdrs/perkins-cli-framework.md
#   - docs/tdrs/perkins-serialization.md
#   - docs/tdrs/perkins-github-operations.md
# conflicts: []
# gaps:
#   - "git remote detection uses subprocess.run(['git', 'remote', 'get-url', 'origin']) — pattern
#     established by validation.py but not explicitly covered by any TDR"
#   - "Placeholder values: repo.name='my-project', repo.description='A project managed by Perkins',
#     repo.github_repo='owner/repo', orchestrator.provider='anthropic',
#     orchestrator.model='claude-opus-4-6', orchestrator.api_key_env='ANTHROPIC_API_KEY'"
#   - "github_repo autodetection on re-init: autodetect if current value equals the placeholder
#     'owner/repo'; preserve if already set to a non-placeholder value"
#   - "Invalid field = a key not present in PerkinsConfig schema; such fields are silently
#     stripped from the output perkins.yaml during re-init"
# escalation_triggers: []
Feature: Perkins Init
  As a developer setting up Perkins for the first time (or re-configuring it),
  I want to run `perkins init` to generate a valid perkins.yaml with placeholder
  values, so that I can start using Perkins without having to write the config
  manually. The command validates all required dependencies first and refuses to
  proceed if any are missing. If perkins.yaml already exists, existing values for
  fields that are present in the PerkinsConfig schema are preserved; fields not
  in the schema are silently stripped; missing fields are filled with placeholders.
  The github_repo field is autodetected from git remote origin unless it is already
  set to a non-placeholder value, in which case the existing value is preserved.

  # ── Happy path ──────────────────────────────────────────────────────────────

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Init creates perkins.yaml with placeholders when no file exists
    Given all dependencies are satisfied and no perkins.yaml exists in the current directory
    When the developer runs perkins init
    Then perkins.yaml is created with placeholder values for all required fields
    And the CLI prints a success message indicating the file was created

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Init autodetects github_repo from git remote origin
    Given the git remote origin URL is "https://github.com/owner/myrepo.git"
    And no perkins.yaml exists
    When the developer runs perkins init
    Then perkins.yaml contains github_repo set to "owner/myrepo"

  @type:edge
  # why: user may not have a git remote configured (new repo, local only) — must not crash
  @status:implemented
  @changed:2026-04-12
  Scenario: Init falls back to placeholder when git remote cannot be detected
    Given no git remote origin is configured in the current repository
    And no perkins.yaml exists
    When the developer runs perkins init
    Then perkins.yaml contains github_repo set to the placeholder value "owner/repo"

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Init preserves valid schema fields from an existing perkins.yaml
    Given perkins.yaml exists with a valid repo.name "my-service" and a non-placeholder github_repo "acme/my-service"
    And all dependencies are satisfied
    When the developer runs perkins init
    Then the resulting perkins.yaml retains repo.name "my-service"
    And the resulting perkins.yaml retains github_repo "acme/my-service"
    And fields that were absent are filled with placeholder values

  @type:edge
  # why: stale or hand-edited perkins.yaml may contain keys removed from PerkinsConfig schema
  @status:implemented
  @changed:2026-04-12
  Scenario: Init strips fields not present in the PerkinsConfig schema
    Given perkins.yaml exists with an unrecognized field "legacy_option: true"
    And all dependencies are satisfied
    When the developer runs perkins init
    Then the resulting perkins.yaml does not contain the field "legacy_option"
    And all valid schema fields are preserved or filled with placeholders

  # ── Dependency failures ──────────────────────────────────────────────────────

  @type:edge
  # why: init must not create a broken config when prerequisites are missing
  @status:implemented
  @changed:2026-04-12
  Scenario: Init aborts when gh CLI is not installed
    Given the gh CLI binary is not present in PATH
    When the developer runs perkins init
    Then the CLI prints an error indicating gh CLI is required
    And no perkins.yaml is written to disk

  @type:edge
  # why: gh not authenticated means perkins start would fail immediately after init
  @status:implemented
  @changed:2026-04-12
  Scenario: Init aborts when gh CLI is not authenticated
    Given the gh CLI is installed but not authenticated
    When the developer runs perkins init
    Then the CLI prints an error indicating gh auth login is required
    And no perkins.yaml is written to disk

  @type:edge
  # why: cliplin.yaml must exist for perkins to have a context store to query
  @status:implemented
  @changed:2026-04-12
  Scenario: Init aborts when cliplin.yaml is missing
    Given no cliplin.yaml is present in the current directory
    When the developer runs perkins init
    Then the CLI prints an error indicating cliplin init must be run first
    And no perkins.yaml is written to disk

  @type:edge
  # why: cliplin-acd knowledge package is required for ACD validation during perkins start
  @status:implemented
  @changed:2026-04-12
  Scenario: Init aborts when cliplin-acd knowledge package is not installed
    Given cliplin.yaml exists but the cliplin-acd knowledge package is not installed
    When the developer runs perkins init
    Then the CLI prints an error indicating the cliplin-acd package must be installed
    And no perkins.yaml is written to disk

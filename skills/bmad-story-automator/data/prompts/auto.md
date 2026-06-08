Execute the BMAD {{label}} workflow for story {{story_id}}.

{{skill_line}}{{workflow_line}}{{instructions_line}}{{checklist_line}}Story file: _bmad-output/implementation-artifacts/{{story_prefix}}-*.md
Auto-apply all discovered gaps in tests.
{{test_command_line}}Always print the full test summary (total / failures / errors / skipped). Do NOT
transcribe test counts into the story prose — the orchestrator records them in a
machine-owned section from the JUnit report.

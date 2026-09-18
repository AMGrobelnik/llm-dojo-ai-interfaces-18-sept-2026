**Do NOT use the Task tool or spawn subagents. Perform all work directly. No exceptions.**

<developer_info>

- Name: <author> | GitHub: <author> | Environment: Linux
  </developer_info>

## Rules

1. Ask for clarification when unsure about implementation details.
2. Solve the exact problem given — no unsolicited alternatives.
3. Explicit exception handling (`@logger.catch`, `logger.exception()`). No silent fallbacks.
4. Test all code before marking complete. Fix errors and re-test until working.
5. No ugly hacks — proper package structure, no `sys.path.append`.
6. Use `config.yaml` for configuration, not CLI args or .env files.
7. Test new libraries in temp files before integrating.
8. Use `pyproject.toml` for deps, not `requirements.txt`.
9. Markdown tables under 70 chars wide.
10. Keyword arguments for functions with 4+ params.
11. Think deeply before complex tasks.

## Python

- **Env**: `uv venv .venv --python=3.12` → `source .venv/bin/activate` → `uv pip install`
- **Structure**: `src/` layout, type hints, `pathlib.Path` for file ops
- **Logging**: loguru with `@retry`, `@logger.catch`, file sink. Format:

  ```text
  GREEN,CYAN,END = "\033[92m","\033[96m","\033[0m"
  format=f"{GREEN}{{time:HH:mm:ss}}{END}|{{level:<7}}|{CYAN}{{function}}{END}| {{message}}"
  ```

- **Testing**: pytest, general-purpose solutions — no hard-coded test-case logic
- **Docs**: Create `EXECUTION_FLOW.md` per project

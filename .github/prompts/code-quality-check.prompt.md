```prompt
---
agent: 'agent'
tools: ['run_in_terminal', 'file_search', 'grep_search']
description: "Code Quality Check: Run ruff + pyright for Python and pyside6-qmllint for QML on changed files (CI-friendly)."
---

# Code Quality Check (CI)

목적: 변경된 파일을 검사하여 Python에는 `ruff`(lint + --fix) 및 `pyright`(type check)를, QML에는 `pyside6-qmllint`(lint)를 실행합니다. CI 환경에서 실패 기준과 출력 형식을 명확히 하도록 권장 옵션을 포함합니다.

## 권장 검사 흐름

- Python 파일(`**/*.py`)에 대해:
  - `uv run python -m ruff check --fix <files>`
  - `uv run python -m pyright`
- QML 파일(`**/*.qml`)에 대해:
  - Windows: `uv run pyside6-qmllint -f --max-warnings=0 --json - <file>` — **auto-apply safe fixes** (`-f`), then re-run with `--json -` to verify results
  - POSIX: `uv run pyside6-qmllint -f --max-warnings=0 --json - <file>` — same auto-apply behavior

## 자동 수정 정책
- 검사 결과에서 자동 수정(또는 안전한 수정)이 가능하다고 판단되면 자동으로 수정하고 변경된 파일을 다시 검사하세요.
  - Python: `uv run python -m ruff check --fix <files>` (수정 후 `uv run python -m pyright`로 타입체크)
  - QML: `uv run pyside6-qmllint -f --max-warnings=0 <file>` (수정 후 `--json -`로 재검사)
- 자동 수정이 불가능하거나 위험한 변경이 필요한 경우, 변경사항 제안을 생성하고(예: PR 코멘트 또는 패치), 수동 검토를 요청하세요.
- 수정은 최소 범위(문제가 있는 파일/라인 한정)로 적용하고, 수정 후에는 테스트, pyright 등을 반드시 재실행하여 회귀가 없는지 확인하세요.

> 권장: `--max-warnings=0`를 사용해 경고도 CI 실패로 처리하고 `--json -`으로 출력하면 결과를 프로그램으로 파싱하기 쉽습니다.


param(
  [Parameter(Mandatory=$true)][string]$ProjectName,
  [string]$ProjectPath = "."
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectPath

$today = (Get-Date).ToString("yyyy-MM-dd")

## Use TASKS.md (tasks) and SESSIONS.md (session logs) as the operational files.

# SESSIONS.md (최신 상단 누적 로그)
@"
## $today
### 오늘 한 일
- SOP 템플릿 부트스트랩 완료

### 결정/근거
- TASKS.md 및 SESSIONS.md를 운영 문서(SoT)로 사용

### 다음 액션
- (필수) 세션 시작 체크리스트 수행
- (선택) Git hooks 경로 설정
"@ | Set-Content -Encoding utf8 "SESSIONS.md"

# AGENTS.md (운영 가이드 요약)
@"
# Environment
* Windows / PowerShell / UTF-8
* 세션 시작 시 Serena 활성화
* 같은 이름 파일 재생성 시 내용 비우고 재작성

# Session SOP
* 시작: Serena → Byterover 조회 → TASKS.md/SESSIONS.md 동기화 → update_plan
* 작업 중: 의미 있는 변경 직후 TASKS.md & SESSIONS.md 갱신
* 종료: update_plan 반영 → CONTROL_PANEL/SESSIONS 갱신 → Byterover 저장

# Python
* uv 사용 권장

# Quick Start
* 새 프로젝트 루트에서 실행:
  `pwsh tools/sop-template/init.ps1 -ProjectName "<이름>"`
"@ | Set-Content -Encoding utf8 "AGENTS.md"

Write-Output "SOP bootstrap files created for $ProjectName"


# 사용 설명서: 내려받아서 내 STEP 파일로 돌리기

GitHub에서 코드를 내려받아, 로컬 AI(Ollama)가 STEP 파일과 같은 형상을 FreeCAD 피처 트리로 다시 만들게 하는
과정을 처음부터 끝까지 적었습니다. Windows 기준입니다. (세부 옵션과 구조는 [README.md](README.md) 참고)

모든 명령은 **압축을 푼 폴더에서** 실행합니다. 이 문서는 `.\fc.cmd`를 씁니다. PowerShell 창과 명령 프롬프트(cmd)
어디서나 똑같이 동작하고, PowerShell 스크립트 실행이 막힌 PC에서도 됩니다.

## 0. 준비물
| 항목 | 설명 |
|---|---|
| Windows 10/11 PC | 인터넷으로 FreeCAD, Ollama, 모델을 받을 수 있어야 합니다 |
| 디스크 여유 | FreeCAD 약 2GB + 모델(qwen3:8b 약 5GB) |
| GPU | 없어도 돌지만 매우 느립니다. NVIDIA GPU(VRAM 8GB 이상)를 권장합니다 |
| STEP/IGES 파일 | 한 폴더에 모아 두면 편합니다 (예: `C:\parts`) |

## 1. 코드 내려받기
1. 브라우저에서 GitHub에 로그인하고 저장소 페이지를 엽니다.
2. 초록색 **Code** 버튼 → **Download ZIP**.
3. 받은 ZIP을 **풀기 전에** 마우스 오른쪽 버튼 → **속성** → 아래쪽 **차단 해제**에 체크 → 확인.
   (이 항목이 안 보이면 건너뛰어도 됩니다. 체크해 두면 뒤에서 "스크립트 차단" 문제가 줄어듭니다.)
4. 압축을 풉니다. `steprecon-main` 폴더가 생깁니다. 경로에 한글이나 공백이 없는 곳을 권장합니다 (예: `C:\work\steprecon-main`).
5. 그 폴더를 탐색기로 열고, 주소창에 `powershell`(또는 `cmd`)을 입력하고 Enter. 그 폴더에서 터미널이 열립니다.

## 2. FreeCAD 설치
아래 둘 중 하나로 설치합니다. 설치 위치는 기본값 그대로 두세요(자동으로 찾습니다).

- 명령으로: `winget install --id FreeCAD.FreeCAD -e`
- 직접: https://www.freecad.org 에서 Windows용 1.x 설치 파일을 받아 실행

확인:
```
.\fc.cmd
```
`FreeCAD python: C:\...\bin\python.exe`가 나오면 찾은 것입니다. `FreeCAD not found`가 나오면
[문제 해결](#8-문제-해결)을 보세요.

## 3. 설치 확인 (테스트)
```
.\fc.cmd run_tests.py
```
마지막 줄에 `12/12 test files passed`가 나오면 정상입니다. 약 20초 걸리고, AI 모델이나 인터넷은 필요 없습니다.

## 4. 로컬 AI(Ollama) 준비
1. https://ollama.com 에서 Ollama를 받아 설치합니다.
2. **컨텍스트 길이를 먼저 늘립니다.** 기본값이 작으면 지침 앞부분이 조용히 잘려서 모델이 엉뚱하게 동작합니다.
   ```
   setx OLLAMA_CONTEXT_LENGTH 16384
   ```
3. Ollama를 **완전히 종료했다가 다시 실행**합니다 (작업 표시줄 오른쪽 아래 Ollama 아이콘 → Quit → 다시 실행).
   터미널도 새로 엽니다.
4. 모델을 받습니다.
   ```
   ollama pull qwen3:8b
   ollama list
   ```
   `ollama list`에 모델이 보이면 준비 끝입니다. GPU 메모리가 넉넉하면 더 큰 모델을 받아 `--model`에 그 이름을 쓰세요.

## 5. 실행

### 5-1. 먼저 한 개로 짧게 확인
데이터가 없어도 시험용 부품을 만들어 볼 수 있습니다.
```
.\fc.cmd make_synth.py --n 5
.\fc.cmd run.py data\synth\synth_003.step --backend openai --model qwen3:8b --turns 10 --out out_test
```
화면에 `[0] pad -> {"ok": true, ...}` 같은 줄이 차례로 나오면 모델이 도구를 쓰고 있는 것입니다.
한 턴에 몇 초~몇 분 걸립니다(GPU에 따라 다름). 마지막에 `converged=True`면 원본과 같아진 것입니다.

### 5-2. 내 STEP 폴더를 같아질 때까지 반복
```
.\fc.cmd run.py C:\parts --backend openai --model qwen3:8b --attempts 5 --turns 30 --out out_parts
```
| 옵션 | 뜻 |
|---|---|
| `C:\parts` | STEP/IGES가 든 폴더(하위 폴더 포함). 파일 하나나 `C:\parts\*.step`도 됩니다 |
| `--turns 30` | 한 번의 시도에서 모델이 만들고-비교하고-고치는 횟수의 상한 |
| `--attempts 5` | 같아지지 않으면 처음부터 다시 시도하는 횟수. 같아지면 바로 다음 파일로 넘어갑니다 |
| `--out out_parts` | 결과 폴더 |
| `--skip-done` | 이미 성공한 파일은 건너뜀. 중간에 끊겼을 때 같은 명령 끝에 붙여 다시 실행 |
| `--profile full` | 도구 24개 전체 사용(회전체·패턴·스윕·다중 바디 등). 큰 모델에서만 권장. 기본은 9개짜리 `basic` |

오래 걸리는 작업입니다. 중간에 멈추려면 `Ctrl+C`를 누르고, 이어서 하려면 `--skip-done`을 붙여 다시 실행하세요.

## 6. 결과 보기
| 파일 | 내용 |
|---|---|
| `out_parts\summary.csv` | 파일별 성공 여부(`converged`), 차이(`xor_pct` %), 몇 번째 시도가 채택됐는지, 걸린 시간. 엑셀로 열립니다 |
| `out_parts\<이름>.FCStd` | 재구성된 모델. FreeCAD에서 열면 왼쪽 트리에 스케치·패드·포켓·구멍 등이 보이고 치수를 고칠 수 있습니다 |
| `out_parts\<이름>.recon.json` | 수렴 여부, XOR %, 만든 피처 목록, 턴 수 |
| `out_parts\<이름>.transcript.json` | 모델과의 대화 전체. 왜 실패했는지 볼 때 씁니다 |
| `out_parts\try1`, `try2` … | 시도별 결과 전부 (`--attempts`가 2 이상일 때) |

성공 기준은 **부피 차이(XOR) 0.1% 미만이고 면 개수가 같은 것**입니다. `converged`가 `False`여도 `.FCStd`는
가장 가까웠던 시도의 것이 남습니다.

## 7. 코드가 갱신됐을 때
1. `out_parts` 같은 **결과 폴더를 다른 곳으로 옮겨 둡니다.**
2. GitHub에서 **Download ZIP**을 다시 받아 새 폴더에 풉니다.
3. `.\fc.cmd run_tests.py`로 확인한 뒤 계속 씁니다. FreeCAD와 Ollama는 다시 설치할 필요가 없습니다.

## PowerShell 스크립트(.ps1)가 실행되지 않을 때
이런 메시지가 나오는 경우입니다.
- `이 시스템에서 스크립트를 실행할 수 없으므로 ... 파일을 로드할 수 없습니다` (running scripts is disabled on this system)
- `... 디지털 서명되지 않았습니다` (is not digitally signed)

**가장 쉬운 방법: `.ps1` 대신 `.cmd`를 씁니다.** 이 문서의 명령은 전부 `.\fc.cmd`라서 그대로 따라 하면 됩니다.
`setup.ps1`이 하는 일(FreeCAD 확인 → 테스트)은 위 2~3단계와 같으므로 실행하지 않아도 됩니다.

`.ps1`을 꼭 써야 한다면 아래 중 하나를 쓰세요.

| 방법 | 명령 | 설명 |
|---|---|---|
| 이번 한 번만 허용 | `powershell -ExecutionPolicy Bypass -File .\fc.ps1 run_tests.py` | 설정을 바꾸지 않습니다 |
| 이 창에서만 허용 | `Set-ExecutionPolicy -Scope Process Bypass` | 창을 닫으면 원래대로 돌아옵니다 |
| 내려받은 파일 차단 해제 | `Get-ChildItem -Recurse \| Unblock-File` | "인터넷에서 받은 파일" 표시를 지웁니다 |
| 래퍼 없이 직접 실행 | `& "$env:LOCALAPPDATA\Programs\FreeCAD 1.1\bin\python.exe" run_tests.py` | FreeCAD의 python을 바로 부릅니다. 설치 위치가 다르면 경로를 바꾸세요 (`C:\Program Files\FreeCAD 1.1\bin\python.exe` 등) |

회사 PC에서 그룹 정책으로 막혀 있으면 위 방법 중 일부가 안 될 수 있습니다. 그때도 `.cmd`와 "직접 실행"은
PowerShell 실행 정책과 무관하게 동작합니다. 정책상 허용되는지는 관리자에게 확인하세요.

## 8. 문제 해결
| 증상 | 조치 |
|---|---|
| `FreeCAD not found` | FreeCAD 1.x 설치 확인. 다른 위치에 설치했다면 `set FREECAD_PYTHON=D:\FreeCAD\bin\python.exe`(cmd) 또는 `$env:FREECAD_PYTHON = "D:\FreeCAD\bin\python.exe"`(PowerShell) 후 다시 실행 |
| `.\fc.cmd`를 찾을 수 없음 | 압축을 푼 폴더(안에 `run.py`가 보이는 곳)에서 터미널을 열었는지 확인 |
| `cannot reach LLM server` | Ollama가 실행 중인지 확인(`ollama list`). 방화벽/보안 프로그램이 `localhost:11434`를 막는지 확인 |
| 모델을 못 찾음 (`model ... not found`) | `ollama pull <모델 이름>`을 했는지, `--model`의 이름이 `ollama list`와 같은지 확인 |
| 모델이 도구를 안 쓰고 말만 함 | `--tool-mode text`를 붙여 봅니다. 그래도 안 되면 더 큰 모델이 필요합니다 |
| 모델이 지침을 무시하는 듯함 | 4-2의 `OLLAMA_CONTEXT_LENGTH` 설정 후 Ollama를 재시작했는지 확인. 실행 시작 때 나오는 `prompt is about N tokens`보다 커야 합니다 |
| 너무 느림 | GPU를 쓰는지 확인(`ollama ps`의 PROCESSOR 열). `--turns`를 줄이거나 더 작은/양자화된 모델 사용 |
| 계속 `converged=False` | `transcript.json`으로 어디서 막히는지 확인. 형상이 회전체·패턴·곡면을 포함하면 `basic` 도구로는 못 만듭니다(`--profile full` + 큰 모델 필요) |
| 테스트가 일부 실패 | FreeCAD 버전이 1.x인지 확인(`.\fc.cmd -c "import FreeCAD; print(FreeCAD.Version()[:3])"`) |

## 알아둘 한계
- 실제 로컬 모델로 성공률을 측정한 적이 아직 없습니다. 8B급 모델이 이 작업을 얼마나 해낼지는 미지수입니다.
- 자유곡면(B-spline)은 피처로 재구성하지 못하고, 그 부분만 원본을 그대로 가져옵니다(`--profile full`에서).
- 나사산, 3차원 경로 스윕, 가이드 곡선 로프트는 지원하지 않습니다.

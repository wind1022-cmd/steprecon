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
1. 브라우저에서 저장소 페이지 https://github.com/wind1022-cmd/steprecon 를 엽니다. 로그인은 필요 없습니다.
2. 초록색 **Code** 버튼 → **Download ZIP**.
   (바로 받기: https://github.com/wind1022-cmd/steprecon/archive/refs/heads/main.zip)
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
마지막 줄에 `20/20 test files passed`가 나오면 정상입니다. 약 20초 걸리고, AI 모델이나 인터넷은 필요 없습니다.

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
| `--reasoning-effort low` | 추론형 모델(gpt-oss 등)이 턴마다 생각하는 양을 줄입니다. **속도가 가장 크게 빨라집니다** |
| `--max-tokens 8192` | 한 턴의 출력 한도(생각 포함, 기본 4096). 화면에 `finish_reason=length`가 보이면 올리세요 |
| `--profile full` | 도구 24개 전체 사용(회전체·패턴·스윕·다중 바디 등). 큰 모델에서만 권장. 기본은 9개짜리 `basic` |

도구 결과마다 원본과의 차이(`state`)가 자동으로 붙고, 같아지는 순간 저절로 저장하고 끝납니다. 모델이 `compare`나 `finish`를 따로 부를 필요가 없습니다.

오래 걸리는 작업입니다. 중간에 멈추려면 `Ctrl+C`를 누르고, 이어서 하려면 `--skip-done`을 붙여 다시 실행하세요.

### 5-3. 로컬 모델 대신 사내 LLM 게이트웨이 쓰기 (Anthropic 방식)
Claude Code를 `ANTHROPIC_BASE_URL`과 `ANTHROPIC_AUTH_TOKEN`으로 연결해 쓰는 게이트웨이가 있다면, 같은 주소와 토큰으로
이 프로그램도 돌릴 수 있습니다. Ollama도, 추가 설치도 필요 없습니다. Claude가 아닌 모델이어도 됩니다.

PowerShell 창에서(그 창에서만 유효하고, 파일에 남지 않습니다):
```
$env:ANTHROPIC_BASE_URL = "https://<게이트웨이 주소>"
$env:ANTHROPIC_AUTH_TOKEN = "<토큰>"
.\fc.cmd run.py C:\parts --backend anthropic --model "<게이트웨이의 모델 이름>" --attempts 3 --turns 20 --out out_parts
```
cmd 창이면 `set ANTHROPIC_BASE_URL=https://<게이트웨이 주소>`, `set ANTHROPIC_AUTH_TOKEN=<토큰>`으로 씁니다.

- 주소와 모델 이름은 Claude Code 설정(`settings.json`의 `env`)에 적힌 값을 그대로 씁니다.
- **토큰을 파일이나 명령 기록, 화면 캡처에 남기지 마세요.** 이 저장소 폴더 안에도 적어 두지 마세요.
- Claude가 아닌 모델은 기본이 `basic`(도구 9개)입니다. 큰 모델이면 `--profile full`을 붙여 보세요.
- 부품의 형상 요약(치수, 면 목록)이 게이트웨이로 전송됩니다. 사내 규정상 허용되는 용도인지 확인하세요.
- 게이트웨이가 OpenAI 방식(`/v1/chat/completions`)도 지원하면 `--backend openai --base-url https://<주소>/v1`과
  `STEPRECON_API_KEY` 환경 변수로도 됩니다.

### 5-4. 결과를 CATIA V5 파트로 옮기기 (시험 단계)
FreeCAD에서 맞춰 낸 피처 트리를 CATIA V5(R34 기준으로 작성)에 그대로 다시 만들어, 히스토리가 있는 `.CATPart`로
저장합니다. CATIA의 기본 자동화 기능만 쓰므로 추가 설치나 라이선스는 필요 없습니다.

1. CATIA V5를 실행해 둡니다.
2. 5-2에서 만든 결과 파일(`.FCStd`)을 지정해 실행합니다.
   ```
   .\fc.cmd to_catia.py "out_parts\test.FCStd" --ref "C:\parts\test.stp"
   ```
3. CATIA에 새 파트가 생기고 스케치, 패드, 포켓이 차례로 만들어집니다. 화면에는 피처마다 한 줄씩 나옵니다.
   - `OK   Pad  variant=0  mismatch=0.000%` : FreeCAD에서의 부피·무게중심과 일치
   - `BAD  ...` : 일치하지 않음. 그 줄과 `(...)` 안의 메시지를 확인
   - `SKIPPED ...` : 아직 옮기지 못하는 피처
4. 결과는 `.FCStd`와 같은 폴더에 `test.CATPart`, `test.catia.stp`(비교용), `test.catia.log`로 남습니다.
   `--ref`를 주면 CATIA가 만든 형상을 원본 STEP과 다시 비교해 `converged`와 `xor`를 알려 줍니다.

- 옮겨지는 피처: 패드, 포켓, 단순 구멍(포켓으로). **필렛·모따기·패턴·회전체 등은 아직 옮기지 못합니다.**
- 이 기능은 CATIA 없이 작성되어 실제 CATIA에서는 검증되지 않았습니다. 오류가 나면 화면 내용과
  `test.catia.log`를 그대로 알려 주세요.
- 매크로만 만들고 직접 실행하려면 `--no-run`을 붙입니다(`test.catvbs`가 생깁니다).

### 5-5. 복잡한 부품: 가공 구멍만 피처로 분리 (AI 불필요)
하우징이나 주조품처럼 형상 전체를 피처로 되살리기 어려운 부품용입니다. 형상은 그대로 두고(고정된 소재 덩어리),
드릴 구멍과 보어만 찾아서 치수가 달린 피처로 바꿉니다. AI 모델을 쓰지 않아 빠르고, 결과는 항상 원본과 같습니다.

```
.\fc.cmd machined.py "C:\parts\housing.stp" --out out_machined
```

결과 `.FCStd`의 트리는 이렇게 됩니다.

```
ImportedBlank   (구멍을 메운 소재 형상, 수정 불가)
Hole_D30        (보어)
Hole_D6_x4      (같은 면에서 뚫은 같은 구멍 4개 = 피처 1개)
...
```

- 구멍의 지름, 위치, 깊이를 FreeCAD에서 바꿀 수 있습니다. 같은 크기의 구멍은 지름 치수 하나로 함께 바뀝니다.
- 화면의 `identical=True xor=0.0%`는 결과가 원본과 같다는 뜻입니다.
- 인식하는 것: 완전한 원통 구멍(관통, 막힌 구멍, 임의 방향, 카운터보어의 각 단).
- 소재에 그대로 남는 것: 드릴 끝의 원뿔, 카운터싱크, 슬롯, 나사산, 곡면 형상, 그리고 다시 깎았을 때 원본과
  어긋나는 구멍(곡면으로 진입하는 구멍 등). 남긴 구멍은 `<이름>.machined.json`의 `skipped`에 적힙니다.

## 6. 결과 보기
| 파일 | 내용 |
|---|---|
| `out_parts\summary.csv` | 파일별 성공 여부(`converged`), 차이(`xor_pct` %), 몇 번째 시도가 채택됐는지, 걸린 시간. 엑셀로 열립니다 |
| `out_parts\<이름>.FCStd` | 재구성된 모델. FreeCAD에서 열면 왼쪽 트리에 스케치·패드·포켓·구멍 등이 보이고 치수를 고칠 수 있습니다 |
| `out_parts\<이름>.recon.json` | 수렴 여부, XOR %, 만든 피처 목록, 턴 수 |
| `out_parts\<이름>.transcript.json` | 모델과의 대화 전체. 왜 실패했는지 볼 때 씁니다 |
| `out_parts\try1`, `try2` … | 시도별 결과 전부 (`--attempts`가 2 이상일 때) |

**스케치 치수**: 저장할 때 모든 스케치에 구속과 치수를 자동으로 넣습니다(수평·수직, 접선, 지름·반지름, 변의 위치,
길이). FreeCAD에서 스케치를 열면 초록색(완전 구속)이고, 치수를 더블클릭해 값을 바꾸면 형상이 따라 바뀝니다.
크기가 같은 원과 호는 치수 하나에 묶여 있어 한 번에 바뀝니다. 화면과 `recon.json`의 `sketches` 항목에
`fully_constrained`(완전 구속된 스케치 수)가 나옵니다. 치수 값은 원본에서 잰 값 그대로입니다.

성공 기준은 **부피 차이(XOR) 0.1% 미만이고 면 개수가 같은 것**입니다. 면 개수는 같은 곡면 위의 면을 합쳐서
셉니다(다른 CAD의 STEP은 원통을 반쪽 두 개로 저장하는 경우가 많아, 그대로 세면 영원히 맞지 않습니다). `converged`가 `False`여도 `.FCStd`는
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
| `(no tool call; nudging)`이 자주 나옴 | 모델이 도구 호출 없이 답한 것입니다. 줄 끝의 `finish_reason=length`는 생각하다가 출력 한도에 걸린 것이니 `--reasoning-effort low` 또는 `--max-tokens 8192`를 쓰세요. 그 외에는 `--tool-mode text`를 시도하세요 |
| 너무 느림 | 추론형 모델이면 `--reasoning-effort low`. `--profile full`을 쓰고 있다면 빼 보세요(지침이 3배 깁니다). GPU를 쓰는지 확인(`ollama ps`의 PROCESSOR 열). `--turns`를 줄이거나 더 작은/양자화된 모델 사용 |
| 계속 `converged=False` | `transcript.json`으로 어디서 막히는지 확인. 형상이 회전체·패턴·곡면을 포함하면 `basic` 도구로는 못 만듭니다(`--profile full` + 큰 모델 필요) |
| FreeCAD에서 열었더니 선(스케치)만 보임 | 예전 버전으로 만든 파일입니다. 모델은 들어 있고 표시만 꺼진 상태입니다. 왼쪽 트리에서 `Body`를 선택하고 스페이스바를 누르면 보입니다. 최신 코드를 다시 받으면 처음부터 솔리드가 보이게 저장됩니다 |
| 테스트가 일부 실패 | FreeCAD 버전이 1.x인지 확인(`.\fc.cmd -c "import FreeCAD; print(FreeCAD.Version()[:3])"`) |

## 알아둘 한계
- 실제 로컬 모델로 성공률을 측정한 적이 아직 없습니다. 8B급 모델이 이 작업을 얼마나 해낼지는 미지수입니다.
- 자유곡면(B-spline)은 피처로 재구성하지 못하고, 그 부분만 원본을 그대로 가져옵니다(`--profile full`에서).
- 나사산, 3차원 경로 스윕, 가이드 곡선 로프트는 지원하지 않습니다.

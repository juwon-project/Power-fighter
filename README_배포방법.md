# 능력자 결투 — 사이트 + 온라인 멀티플레이 배포

이 ZIP은 사용자가 제공한 **「능력자 결투 (1).html」 원본**을 수정하지 않고 `index.html`로 담았고, 원본 게임의 온라인 로비 통신 방식에 맞춘 `server.py`를 추가한 버전입니다. **3D OPENFIRE가 아니라 업로드한 2D 게임**입니다.

## 가장 쉬운 공개 배포: GitHub + Render

1. [github.com](https://github.com/)에서 로그인 → `New repository` → `ability-duel-online`이라는 저장소를 생성합니다. 이 프로젝트가 공개되는 게 싫으면 `Private`으로 만들 수 있습니다.
2. 압축을 풀고 **`index.html`, `server.py`, `requirements.txt`, `render.yaml`**을 저장소 최상위에 올립니다. GitHub 웹에서 `Add file` → `Upload files`를 이용할 수 있습니다. (나머지 파일도 올려도 됩니다.)
3. [dashboard.render.com](https://dashboard.render.com/)에 로그인 → `New` → `Web Service` → GitHub 저장소 연결.
4. 설정: Language `Python 3`, Build Command `pip install -r requirements.txt`, Start Command `python server.py`, Instance `Free`(시험용), Health Check `/health`.
   - `render.yaml`을 활용하고 싶다면 Render의 `New` → `Blueprint`에서 저장소를 선택할 수도 있습니다.
5. `Create Web Service` 후 `Live`가 되면 `https://<서비스이름>.onrender.com` 주소를 공유합니다.
6. 친구 2명이 **같은 사이트**에 접속 → 게임의 **온라인 1vs1** 선택 → 한 명이 방 만들기, 다른 사람은 같은 서버의 방 목록에서 입장 → 각자 캐릭터 선택 후 경기 진행.
7. 보스 레이드는 **최대 4명**이 같은 방식으로 입장합니다. 원본 게임에 보스 레이드 AI 동료 옵션이 있다는 점에 유의하세요.

**핵심:** HTML에 이미 `wss://현재사이트주소/ws`라는 서버 기본값이 구현돼 있습니다. 이 프로젝트는 같은 주소에서 웹사이트와 WebSocket 게임 서버를 함께 제공하므로, 배포 후에는 별도 서버 주소를 입력할 필요가 없습니다. 단, 브라우저에 이전 서버 주소가 저장되어 있으면 온라인 로비의 `서버` 칸을 `wss://<서비스이름>.onrender.com/ws`로 바꾸세요.

## 로컬 사전 테스트

Python 3.11+ 설치 후 ZIP 압축을 풀고 터미널에서:

```bash
pip install -r requirements.txt
python server.py
```

브라우저 두 개의 탭에서 `http://localhost:10000`을 열어 온라인 로비 연결을 테스트합니다. Windows에서는 `start_windows.bat`을 실행해도 됩니다.

## 무료 플랜 주의사항

- Render 무료 Web Service는 15분간 HTTP 요청 또는 WebSocket 메시지가 없으면 멈추며, 다시 접속 시 기동 시간이 걸릴 수 있습니다. 실제 사용량·제한은 Render 공식 문서를 확인하세요.
- 서버 재시작/배포/수면 중 모든 방과 접속 정보가 초기화됩니다. 방 상태는 메모리 저장입니다.
- 이 서버는 **친구끼리 시험하는 웹 게임 서버**입니다. 입력을 전달하는 relay 방식으로, 고급 대전용 치트 방지·입력 검증·계정 로그인·전적 DB·지역별 서버·서버 권위 판정은 없습니다.
- 서버는 하나의 프로세스에서 방을 관리하도록 설계했습니다. 복수 인스턴스/자동 스케일링을 사용하려면 Redis 등 외부 공유 상태 구성이 필요합니다.
- 1vs1과 보스 레이드는 원본 HTML에 구현된 온라인 모드이며, 이 패키지에서 새롭게 게임플레이를 제작한 것은 아닙니다.

## 구성 파일

- `index.html`: 원본 2D 게임 (수정 없이 복사)
- `server.py`: 사이트 제공 + WebSocket 온라인 로비·방 생성·입장·게임 입력 전달
- `requirements.txt`: Python 패키지
- `render.yaml`: Render 설정 자동화 파일
- `start_windows.bat`: 로컬 시작 스크립트

## 문제 해결

- 사이트가 안 열림: Render `Logs`에 서버 오류 여부 확인. 포트는 `PORT` 환경변수를 사용해야 합니다.
- 온라인 접속 실패: `https://` 사이트 주소와 `wss://` 서버 주소를 사용했는지 확인. `wss://<주소>/ws` 형태입니다.
- 목록에 방이 없음: 둘 다 같은 `onrender.com` 사이트에 접속했는지 확인.
- 로비는 열리는데 경기 지연: 네트워크 지연·서버 위치가 원인일 수 있습니다. 이 게임의 입력 동기화는 lockstep 방식이라 지연이 큰 참가자에 맞춰 멈출 수 있습니다.
- 게임이 이 HTML 버전과 다름: 이 패키지는 업로드한 「능력자 결투 (1).html」을 사용합니다. OPENFIRE v0.2 3D 게임 배포에는 **별도 서버 프로토콜**이 필요합니다.

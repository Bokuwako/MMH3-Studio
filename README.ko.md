# MMH3 Studio

MiniMax H3 영상 제작용 로컬 작업실. 렌더링은 ComfyUI, 프롬프트 작성은 Ollama가 맡습니다.

## 실행

1. ComfyUI(8188)와 Ollama(11434)를 실행합니다.
2. `start.cmd`를 실행하고 `http://127.0.0.1:8791`에 접속합니다.
3. 레퍼런스를 업로드하고 용도를 지정합니다. 디렉터에서 샷을 구성하고 Ollama 모델로 프롬프트를 작성합니다.
4. 프로덕션에서 엔진을 고르고 사전 검사 후 생성합니다.

## 생성 엔진

- **Normal:** 클립 하나. 기존 H3 파이프라인(`workflows/current.json`)을 기반으로 하고, 고화질 마감은 켜기/끄기만 있습니다. 오디오는 베이스 패스의 latent에서 디코딩합니다.
- **Continuum:** 여러 클립을 한 번의 실행으로 이어서 생성합니다. H3 Continuum-Plus V3.4 샘플러 → `refine_state` → Upscaler-Plus 3D refine → Assemble + Seam 순서로, 제작자의 방식 그대로 연결합니다. 앞 클립의 마지막 프레임(기본 39프레임)이 다음 클립의 시작으로 이어집니다. 이음매 처리(Seam `Auto`)는 경계의 순간적인 번쩍임만 교체하며, 클립 전체의 색·밝기 차이는 보정하지 않습니다.

## MMH3 Studio 전용 노드

`custom_nodes/ComfyUI-MMH3-Studio-Nodes`. 다른 노드팩의 파일은 수정하지 않고 상속으로만 바꿉니다.

- `MMH3S_ContinuumSampler`: V3.4가 숨긴 목소리 참조(Reference Audio) 입력을 다시 열고, 클립마다 인코딩 뒤 텍스트 인코더를 내립니다.
- `MMH3S_DirectorGuide`: DaSiWa Director Guide를 Core H3 노드에 이름으로 연결하고, 인코딩 뒤 텍스트 인코더를 내립니다.

이 폴더가 없으면 Studio는 원래 노드로 돌아가며, 목소리 참조와 텍스트 인코더 해제는 동작하지 않습니다.

## 기능

- 이미지·음성·영상 참조, 용도 문장, 자르기 구간, 이미지 역할·대상·적용 샷, 드래그로 순서 변경.
- REF2VA, T2VA, I2VA, FL2VA, L2VA.
- 모델·LoRA 선택(긴 목록은 검색 가능), 터보 LoRA 프로필, 추가 LoRA, FaceRefine, 후처리.
- 생성 중 미리보기: 초 단위로 길이를 정하고 실제 속도로 재생합니다. taeh3는 앞에서부터 디코딩하므로, 짧게 정하면 클립 앞부분이 보입니다.
- 렌더 대기열: ComfyUI처럼 여러 작업을 걸어 둘 수 있습니다.
- 작업 기록: 사용한 프롬프트와 설정 보기, 설정만 또는 레퍼런스까지 불러오기, 첫·마지막 프레임을 레퍼런스로 가져오기.
- LLM 대화: 프로덕션 설정을 읽고 프롬프트를 함께 다듬습니다. 적용은 수동이며 적용한 버전은 모두 저장됩니다.
- Ollama 작업 전 ComfyUI 모델 해제, 영상 생성 전 Ollama 모델 해제. 렌더 중에는 LLM 작업을 시작하지 않습니다. 수동 Kill Switch는 워커·캐시까지 정리합니다.
- 사이드바의 재시작·종료 버튼.

## 검사 범위

- 프레임 격자, 참조 개수·길이, 미디어 경로, 모델 선택, Continuum 오디오 격자(이어받는 프레임 수는 3의 배수)를 큐 제출 전에 검사합니다. ComfyUI도 제출 시 검증합니다.
- 5초 요청은 H3 프레임 격자에 따라 124프레임(약 5.17초)이 됩니다.
- VRAM 부족, 모델 파일 내부 불일치, 영상의 의미적 오류까지 보장하지 않습니다.
- 노드 팩 업데이트 뒤에는 짧은 2클립 렌더로 목소리 참조와 텍스트 인코더 해제 로그(`mmh3 studio: text encoder released`)를 확인하세요.

## 데이터

`data/workspace.json`: 편집 상태. `data/jobs.json`: 실행 기록. `data/chats/`: LLM 대화. `data/frames/`: 작업별 첫·마지막 프레임. `data/last_graph.json`: 마지막 제출 그래프.
생성물은 ComfyUI output에 저장합니다.

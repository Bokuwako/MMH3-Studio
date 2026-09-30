# MMH3 Studio

MiniMax H3 영상 제작용 로컬 작업실입니다. 렌더링은 ComfyUI, 프롬프트 작성은 Ollama가 맡습니다.
기능과 사용법은 [README.ko.md](README.ko.md)를 보세요.

이 저장소에는 **코드만** 들어 있습니다. 모델, 에셋, 작업 데이터는 포함하지 않습니다.

## 요구 사항

- Windows, NVIDIA GPU (RTX 5070 Ti 16GB에서 검증)
- RAM 64GB 권장. 긴 Continuum 영상을 고화질로 뽑을 때는 가상 메모리(페이지 파일)를 32GB 이상 잡아 두세요.
- **ComfyUI portable v0.37.0 이상** (MiniMax H3 노드가 코어에 들어 있는 버전)
- [git](https://git-scm.com/) (노드팩 자동 설치에 필요)
- [Ollama](https://ollama.com/) (프롬프트 작성)

## 설치

1. 이 저장소를 받습니다. 위치는 어디든 됩니다.
2. `install.cmd`를 실행하고 ComfyUI 폴더 경로(`main.py`가 있는 폴더)를 입력합니다.
   - Studio 전용 노드팩을 ComfyUI에 복사합니다.
   - 아래 노드팩 중 **없는 것만** 검증된 버전으로 받아 설치합니다. 이미 있는 노드팩은 건드리지 않습니다.
3. 아래 **모델**을 ComfyUI `models` 폴더에 넣습니다.
4. Ollama를 설치하고 프롬프트 작성용 모델을 받습니다. 레퍼런스 이미지를 읽게 하려면 비전을 지원하는 모델이 필요합니다.
5. ComfyUI를 재시작하고 `start.cmd`로 Studio를 실행합니다. 브라우저에서 `http://127.0.0.1:8791`이 열립니다.
6. Studio 설정에서 사용할 모델, 텍스트 인코더, VAE, LoRA를 고릅니다. 템플릿에는 모델이 지정되어 있지 않습니다.

## 필요한 커스텀 노드

`install.cmd`가 설치하는 목록입니다. 직접 설치해도 됩니다. 버전이 다르면 동작이 달라질 수 있습니다.

| 노드팩 | 저장소 | 검증 버전 |
|---|---|---|
| MMH3 Studio Nodes | 이 저장소 `custom_nodes/` | 포함 |
| Prompt Director | [Bokuwako/ComfyUI-MinimaxH3-PromptDirector](https://github.com/Bokuwako/ComfyUI-MinimaxH3-PromptDirector) | v3.0.1 |
| H3 Continuum Plus | [xmarre/ComfyUI-H3-Continuum-Plus](https://github.com/xmarre/ComfyUI-H3-Continuum-Plus) | 3.4.4 (`e870875`) |
| H3 Latent Upscaler Plus | [xmarre/Comfyui_Minimax_h3_latent_Upscaler-Plus](https://github.com/xmarre/Comfyui_Minimax_h3_latent_Upscaler-Plus) | v0.2.1 |
| DaSiWa Nodes | [darksidewalker/ComfyUI-DaSiWa-Nodes](https://github.com/darksidewalker/ComfyUI-DaSiWa-Nodes) | 0.4.65 (`1163c8c`) |
| MAINodes | [matlowai/ComfyUI-MAINodes](https://github.com/matlowai/ComfyUI-MAINodes) | 1.1.3 (`f4868b4`) |
| H3 FaceRefine | [Carasibana/ComfyUI-H3-FaceRefine](https://github.com/Carasibana/ComfyUI-H3-FaceRefine) | 1.1.2 (`d8521d1`) |
| H3 NativeAudioLock | [Shrek3OnVH5/MiniMax-H3-NativeAudio-MusicVideo-Workflow](https://github.com/Shrek3OnVH5/MiniMax-H3-NativeAudio-MusicVideo-Workflow) 안의 `custom_nodes/ComfyUI-H3-NativeAudioLock` | `11a95f6` |
| EasyUse Anima | [n0va39/ComfyUI-EasyUseAnima](https://github.com/n0va39/ComfyUI-EasyUseAnima) | 1.2.2 (`38b2a4c`) |
| KJNodes | [kijai/ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes) | 1.5.2 (`d3cfe21`) |
| VideoHelperSuite | [Kosinkadink/ComfyUI-VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite) | 1.7.9 (`3234937`) |
| Easy-Use | [yolain/ComfyUI-Easy-Use](https://github.com/yolain/ComfyUI-Easy-Use) | v1.4.1 |
| Impact Pack | [ltdrdata/ComfyUI-Impact-Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack) | 8.28.3 (`429d015`) |
| Impact Subpack | [ltdrdata/ComfyUI-Impact-Subpack](https://github.com/ltdrdata/ComfyUI-Impact-Subpack) | 1.3.5 (`50c7b71`) |

각 노드팩의 라이선스는 해당 저장소를 따릅니다.

## 모델

파일 이름은 원하는 것을 쓰고 Studio 설정에서 고르면 됩니다.

| 종류 | 폴더 | 받을 곳 |
|---|---|---|
| MiniMax H3 확산 모델 | `models/diffusion_models/` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) 또는 호환 모델 |
| H3 텍스트 인코더 | `models/text_encoders/` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) |
| 영상 VAE, 오디오 VAE | `models/vae/` | [Comfy-Org/MiniMax-H3 · vae](https://huggingface.co/Comfy-Org/MiniMax-H3/tree/main/vae) |
| 미리보기용 `taeh3.safetensors` | `models/vae_approx/` | H3용 Tiny VAE |
| 잠재 업스케일러 `minimax_h3_latent_upscaler_3d_fp16.safetensors` | `models/latent_upscale_models/` | [Upscaler Plus 저장소](https://github.com/xmarre/Comfyui_Minimax_h3_latent_Upscaler-Plus) 안내 |
| 터보 LoRA (선택, 속도 향상) | `models/loras/` | [Kijai/MiniMax-H3_comfy · loras](https://huggingface.co/Kijai/MiniMax-H3_comfy/tree/main/loras) |
| 얼굴 검출 `face_yolov8m.pt`, `person_yolov8m-seg.pt` (FaceRefine) | `models/ultralytics/bbox`, `models/ultralytics/segm` | Impact Subpack 안내를 따름 |
| 레퍼런스 탭 (선택) | 각 모델 폴더 | Anima 또는 Qwen Image Edit 모델 |

## 알려진 제한

- 프로젝트(체인) 기능은 H3 Project Suite 노드팩이 필요하며, 이 배포에는 포함하지 않았습니다. Normal과 Continuum 엔진은 없이 동작합니다.
- 긴 Continuum 영상을 고화질로 뽑으면 마지막 조립 단계에서 RAM을 많이 씁니다. 고화질 1MP 기준 영상 1초당 약 0.3GB입니다.
- 노드팩을 업데이트한 뒤에는 짧은 2클립 렌더로 먼저 확인하세요.

## 라이선스

MIT. [LICENSE](LICENSE)를 보세요.

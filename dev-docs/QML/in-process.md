✅ 무엇을 추가했나
1. Python AppController (POC stub)
  qml_bridge.py — AppController(QObject) 기본 프로퍼티/슬롯/시그널 포함 (generation 관리 스텁 포함) ✅
2. Viewer 호스트 위젯
  viewer_host.py — ViewerHostWidget(QWidget) : 내부에 QQuickView를 생성하고 createWindowContainer로 임베드하는 최소 동작 구현 ✅
3. 초기 QML Viewer 페이지
  ViewerPage.qml — Flickable + Image + 상태 오버레이(POC용) ✅
4. 기본 테스트 파일
  test_qml_viewer_m0.py — AppController 인스턴스화 테스트 및 ViewerHostWidget의 QML 소스 위치 검사(기본 검증) ✅

📝 구현/디자인 노트
* M0은 POC용 최소 안전 경로입니다: C++ QQuickItem 기반 고성능 구현은 다음 단계(M3 이후)로 교체 권장.
* Fullscreen 동작(Windows) 및 텍스처 업로드/세대(generation) discard는 아직 미연결 상태 — 다음 단계에서 AppController ↔ ImageEngine 연동이 필요합니다.
* 테스트는 경량 검증(구성요소 생성/소스 설정) 수준이며, 실제 decode→QML 경로는 통합 테스트로 확장해야 합니다.

🔧 다음 제안 (원하면 바로 진행)
* main.py에 AppController 인스턴스 등록 및 ViewerHostWidget을 중앙 위젯으로 추가 (M0 완료) 🔁
* AppController → ImageEngine.request_decode 연결(기본 preview flow) 및 imageReady 신호로 QML에 이미지 푸시 (M1) ▶ 제가 연결할까요?
* Fullscreen POC: detached QQuickView 전환/테스트 (Windows VM에서 확인) 🔍
---

1. AppController + Viewer host integrated into main (M0)
* qml_bridge.py
  AppController: generation tracking, requestPreview/requestRefine call into engine, onEngineImageReady slot that converts engine pixmaps to QImage and emits imageReady only when the request is current.
* viewer_host.py
  ViewerHostWidget updated to accept an app_controller context property, embed the QML via QQuickView → createWindowContainer, and added enter_fullscreen / exit_fullscreen to show a detached full-screen QQuickView.
* main.py
  When the CLI flag `--qml-poc` is passed, ImageViewer creates an AppController, connects `engine.image_ready` to it, and replaces the central widget with `ViewerHostWidget`. Fullscreen toggles are delegated to the viewer host when present.
2. POC QML page and tests (M0 → M3 scaffolding)
* ViewerPage.qml — minimal Flickable + Image + status overlay for POC.
* test_qml_viewer_m0.py — tests to validate:
  ViewerHostWidget loads QML source
  main creates ViewerHostWidget when env var is set
  requestPreview calls engine.request_decode
  onEngineImageReady emits imageReady (matching path/generation)
  Fullscreen detach/restore behavior (detached view created and container visibility toggled)

* The POC uses QQuickView instances for embedded and detached fullscreen views. For production you may prefer a more robust texture-sharing approach (re-using a single view/texture), or a native C++ ViewerItem implementation for best performance.
* AppController uses simple generation logic. If you want per-path multiple simultaneous generations or richer priority/epoch semantics, we should expand the generation and job-id model.
* The tests are lightweight unit/integration checks. I recommend adding headless integration runs on Windows VM for fullscreen flicker verification (manual+scripted).
* Next logical step (if you want): wire AppController.imageReady to QML (e.g., via a small QML handler that sets Image source to data URL or uses a QQuickImageProvider) so the POC can show live frames. I can implement that in the QML side or via a provider next.

Shall I:

* Connect AppController.imageReady to QML (e.g., expose an image provider or push a base64/data URL into the QML Image source), or
* Convert the QML Viewer from Image to using a C++ ViewerItem (higher effort, higher performance)?
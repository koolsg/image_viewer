from image_viewer.qml_bridge import AppController


def test_app_controller_navigation_updates_index_and_path():
    ctrl = AppController(engine=None)
    ctrl._on_engine_file_list_updated(["C:/a.jpg", "C:/b.jpg", "C:/c.jpg"])

    assert ctrl.currentIndex == 0
    assert ctrl.currentPath.replace("\\", "/").endswith("/a.jpg")

    ctrl.nextImage()
    assert ctrl.currentIndex == 1
    assert ctrl.currentPath.replace("\\", "/").endswith("/b.jpg")

    ctrl.lastImage()
    assert ctrl.currentIndex == 2
    assert ctrl.currentPath.replace("\\", "/").endswith("/c.jpg")

    ctrl.prevImage()
    assert ctrl.currentIndex == 1

    ctrl.firstImage()
    assert ctrl.currentIndex == 0


def test_close_view_window_exits_view_mode():
    ctrl = AppController(engine=None)
    ctrl._set_view_mode(True)
    ctrl.closeViewWindow()
    assert ctrl.viewMode is False

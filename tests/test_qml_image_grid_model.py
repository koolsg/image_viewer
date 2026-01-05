from image_viewer.qml_models import QmlImageGridModel


def test_qml_image_grid_model_filters_images_and_builds_thumb_url():
    m = QmlImageGridModel()
    m.set_entries(
        [
            {"path": "C:/a.jpg", "name": "a.jpg", "suffix": "jpg", "size": 10, "mtime_ms": 1000, "is_image": True},
            {"path": "C:/note.txt", "name": "note.txt", "suffix": "txt", "size": 1, "mtime_ms": 1000, "is_image": False},
        ]
    )

    assert m.rowCount() == 1

    idx = m.index(0, 0)
    assert m.data(idx, int(m.Roles.Name)) == "a.jpg"

    thumb_url = m.data(idx, int(m.Roles.ThumbUrl))
    assert isinstance(thumb_url, str)
    assert thumb_url.startswith("image://thumb/")


def test_qml_image_grid_model_updates_thumb_rows_bumps_gen_and_resolution():
    m = QmlImageGridModel()
    m.set_entries(
        [
            {"path": "C:/a.jpg", "name": "a.jpg", "suffix": "jpg", "size": 10, "mtime_ms": 1000, "is_image": True},
        ]
    )

    idx = m.index(0, 0)
    gen0 = m.data(idx, int(m.Roles.ThumbGen))

    m.update_thumb_rows([
        {"path": "C:/a.jpg", "width": 100, "height": 50},
    ])

    gen1 = m.data(idx, int(m.Roles.ThumbGen))
    assert gen1 == gen0 + 1
    assert m.data(idx, int(m.Roles.ResolutionText)) == "100x50"

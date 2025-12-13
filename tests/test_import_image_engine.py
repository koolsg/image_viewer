def test_import_image_engine():
    import importlib, sys, traceback
    try:
        import image_viewer.image_engine.engine as eng_mod
    except Exception as exc:
        traceback.print_exc()
        assert False, f"Import failed: {exc}"
    assert getattr(eng_mod, 'ImageEngine', None) is not None

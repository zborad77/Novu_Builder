import inspect

import app.modules.analysis.ai.analysis_service as analysis_service_mod
import app.modules.exports.export_service as export_service_mod


def test_analysis_service_uses_storage_backend_reader():
    source = inspect.getsource(analysis_service_mod)
    assert "read_storage_file" in source
    assert "generate_presigned_url" in source
    assert "STORAGE_ROOT" not in source
    assert "local_photo_storage" not in source


def test_export_service_uses_storage_backend_abstraction():
    source = inspect.getsource(export_service_mod)
    assert "write_storage_file" in source
    assert "read_storage_file" in source
    # NC-007 kap. 6.3: downloadUrl ukazuje na /files/exports/{id}, export
    # service už podepsané URL úložiště nevyrábí.
    assert "generate_presigned_url" not in source
    assert "export_file_url" in source
    assert "EXPORTS_ROOT" not in source
    assert "_sync_write_storage_file" not in source
    assert "get_public_url" not in source

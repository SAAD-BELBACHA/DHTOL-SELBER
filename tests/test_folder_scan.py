from dhtol_analyzer.folder_scan import scan_folder, validate_folder


def test_scan_counts_only_supported_files(tmp_path):
    (tmp_path / "run.json").write_text("{}", encoding="utf-8")
    (tmp_path / "board.log").write_text("line", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("ignored", encoding="utf-8")

    result = scan_folder(tmp_path)

    assert result.counts == {".json": 1, ".log": 1}
    assert len(result.files) == 2


def test_validate_rejects_missing_folder(tmp_path):
    root, error = validate_folder(str(tmp_path / "missing"))

    assert root is None
    assert error == "Folder does not exist."

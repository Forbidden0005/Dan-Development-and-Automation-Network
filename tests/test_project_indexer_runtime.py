from pathlib import Path


def test_project_scanner_summary_and_prompt_are_ascii_safe(tmp_path):
    from project_indexer import ProjectScanner

    root = tmp_path / "sample"
    root.mkdir()
    (root / "app.py").write_text(
        "import os\n\nclass Demo:\n    pass\n\ndef run_job():\n    return 1\n",
        encoding="utf-8",
    )

    project_map = ProjectScanner(root).scan()

    summary = project_map.summary()
    prompt = project_map.to_prompt()

    summary.encode("cp1252")
    prompt.encode("cp1252")
    assert "Loaded: sample" in summary
    assert "FILE MAP  (* = entry point)" in prompt
    assert "Demo  ->  app.py" in prompt
    assert "run_job()  ->  app.py" in prompt


def test_project_scanner_skips_hidden_dirs_and_minified_assets(tmp_path):
    from project_indexer import ProjectScanner

    root = tmp_path / "sample"
    root.mkdir()
    (root / "app.py").write_text("def run_job():\n    return 1\n", encoding="utf-8")
    (root / "bundle.min.js").write_text("function x(){}", encoding="utf-8")

    hidden_dir = root / ".hidden"
    hidden_dir.mkdir()
    (hidden_dir / "secret.py").write_text("def nope():\n    return 0\n", encoding="utf-8")

    project_map = ProjectScanner(root).scan()
    indexed_paths = {file_info.rel_path for file_info in project_map.files}

    assert "app.py" in indexed_paths
    assert "bundle.min.js" not in indexed_paths
    assert ".hidden/secret.py" not in indexed_paths
    assert project_map.total_files == 1

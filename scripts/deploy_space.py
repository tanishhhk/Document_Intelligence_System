"""Publish the API to a Hugging Face Space, which builds and runs the Dockerfile.

    HF_TOKEN=... HF_SPACE=user/space-name python scripts/deploy_space.py

Uploads only what the image needs (no tests, documents or local data), plus
the Space's README card. Secrets such as SECRET_KEY and OPENROUTER_API_KEY are
set in the Space's settings, never uploaded.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
INCLUDE = ["Dockerfile", "requirements.txt", "alembic.ini", "app", "migrations"]
CARD = """---
title: Document Intelligence API
emoji: 📄
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 8000
pinned: false
short_description: API for the guruCool document assistant
---

The API behind the guruCool web app. Source: https://github.com/{repository}
"""


def main() -> None:
    token, space = os.environ.get("HF_TOKEN"), os.environ.get("HF_SPACE")
    if not token or not space:
        sys.exit("Set HF_TOKEN and HF_SPACE (for example user/document-intelligence-api).")
    repository = os.environ.get("GITHUB_REPOSITORY", "tanishhhk/Document_Intelligence_System")

    api = HfApi(token=token)
    api.create_repo(space, repo_type="space", space_sdk="docker", exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        for name in INCLUDE:
            source = ROOT / name
            if source.is_dir():
                shutil.copytree(source, Path(folder) / name, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(source, Path(folder) / name)
        (Path(folder) / "README.md").write_text(CARD.format(repository=repository), encoding="utf-8")
        api.upload_folder(
            repo_id=space,
            repo_type="space",
            folder_path=folder,
            commit_message=f"Deploy {os.environ.get('GITHUB_SHA', 'local')[:12]}",
            delete_patterns=["app/**", "migrations/**"],
        )
    print(f"Uploaded to https://huggingface.co/spaces/{space}")


if __name__ == "__main__":
    main()

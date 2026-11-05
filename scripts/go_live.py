"""Put guruCool online: the API on a Hugging Face Space, the web app on GitHub Pages.

    python scripts/go_live.py

Reads HF_TOKEN, GROQ_API_KEY and OPENROUTER_API_KEY from .env, then:

1. creates the Space and uploads the API (scripts/deploy_space.py);
2. stores its secrets in the Space settings, never in the repository: a new
   random SECRET_KEY, the model keys, the allowed web origin;
3. gives GitHub the HF_TOKEN secret and the HF_SPACE and API_URL variables,
   so later pushes to main redeploy both by themselves;
4. turns on GitHub Pages and builds the web app against the Space.

Safe to run again: it updates what exists. Needs the GitHub CLI signed in.
"""
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
SPACE_NAME = "gurucool-api"


def gh(*args, stdin=None, check=True):
    result = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True)
    if check and result.returncode != 0:
        sys.exit(f"gh {' '.join(args[:2])} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def main() -> None:
    env = dotenv_values(ROOT / ".env")
    token = env.get("HF_TOKEN", "").strip()
    groq = env.get("GROQ_API_KEY", "").strip()
    openrouter = env.get("OPENROUTER_API_KEY", "").strip()
    if not token.startswith("hf_"):
        sys.exit("Add HF_TOKEN=hf_... (a Write token from huggingface.co/settings/tokens) to .env first.")
    if not (groq or openrouter):
        sys.exit("Add GROQ_API_KEY or OPENROUTER_API_KEY to .env first.")

    api = HfApi(token=token)
    owner = api.whoami()["name"]
    space = f"{owner}/{SPACE_NAME}"
    api_url = f"https://{owner.lower().replace('_', '-')}-{SPACE_NAME}.hf.space"
    repository = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")
    pages_origin = f"https://{repository.split('/')[0].lower()}.github.io"
    print(f"Space {space}, API {api_url}, web app {pages_origin}/{repository.split('/')[1]}/")

    print("1/4 Uploading the API to the Space")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "deploy_space.py")],
        env={**os.environ, "HF_TOKEN": token, "HF_SPACE": space, "GITHUB_REPOSITORY": repository},
        check=True,
    )

    print("2/4 Storing the Space secrets")
    space_secrets = {
        "SECRET_KEY": secrets.token_urlsafe(48),
        "CORS_ORIGINS": json.dumps([pages_origin]),
        "DATABASE_URL": "sqlite:////data/db/dis.db",
        "LLM_PROVIDERS": "groq,openrouter",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "720",
        "LOG_FORMAT": "json",
    }
    if groq:
        space_secrets["GROQ_API_KEY"] = groq
    if openrouter:
        space_secrets["OPENROUTER_API_KEY"] = openrouter
    # Running this again sets a new SECRET_KEY, which signs everyone out once.
    for key, value in space_secrets.items():
        api.add_space_secret(space, key, value)

    print("3/4 Connecting GitHub to the Space")
    gh("secret", "set", "HF_TOKEN", "--repo", repository, stdin=token)
    gh("variable", "set", "HF_SPACE", "--repo", repository, "--body", space)
    gh("variable", "set", "API_URL", "--repo", repository, "--body", api_url)

    print("4/4 Publishing the web app")
    gh("api", "-X", "POST", f"repos/{repository}/pages", "-f", "build_type=workflow", check=False)
    gh("api", "-X", "PUT", f"repos/{repository}/pages", "-f", "build_type=workflow", check=False)
    gh("workflow", "run", "pages.yml", "--repo", repository, "--ref", "main")

    api.restart_space(space)
    print(
        "\nDone. The Space builds for about 10 minutes the first time; the web app publishes in about 2.\n"
        f"  Web app: {pages_origin}/{repository.split('/')[1]}/\n"
        f"  API:     {api_url}/health\n"
        f"  Build:   https://huggingface.co/spaces/{space}"
    )


if __name__ == "__main__":
    main()

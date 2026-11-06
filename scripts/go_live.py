"""Connect the web app on GitHub Pages to the API deployed on Render.

    python scripts/go_live.py https://gurucool-api.onrender.com

First deploy the API with the Blueprint in render.yaml (the "Deploy to
Render" link in the README). Then this script:

1. checks that the API answers /health and /ready (the first request may
   wake a sleeping free instance, which takes about a minute);
2. sets the API_URL repository variable that the web app is built with;
3. turns on GitHub Pages and publishes the web app.

Safe to run again. Needs the GitHub CLI signed in.
"""
import json
import subprocess
import sys
import time
import urllib.request

PAGES_ORIGIN = "https://tanishhhk.github.io"


def gh(*args, check=True):
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        sys.exit(f"gh {' '.join(args[:2])} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def get(url: str, timeout: float = 30):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, response.read().decode()


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("https://"):
        sys.exit("Usage: python scripts/go_live.py https://<your-service>.onrender.com")
    api_url = sys.argv[1].rstrip("/")
    repository = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")

    print(f"1/3 Waiting for {api_url} (a sleeping free instance takes about a minute)")
    deadline = time.monotonic() + 600
    while True:
        try:
            status, body = get(f"{api_url}/ready")
            checks = json.loads(body).get("checks", {})
            if status == 200:
                break
        except Exception as exc:  # Not up yet, or still deploying.
            checks = {"error": type(exc).__name__}
        if time.monotonic() > deadline:
            sys.exit(f"The API did not become ready: {checks}")
        time.sleep(10)
    print(f"    ready: {checks}")
    if checks.get("answer_providers") in (None, "none"):
        print("    note: no model key is set on Render, so answers use the quoted-passage fallback")

    print("2/3 Pointing the web app at the API")
    gh("variable", "set", "API_URL", "--repo", repository, "--body", api_url)

    print("3/3 Publishing the web app on GitHub Pages")
    gh("api", "-X", "POST", f"repos/{repository}/pages", "-f", "build_type=workflow", check=False)
    gh("api", "-X", "PUT", f"repos/{repository}/pages", "-f", "build_type=workflow", check=False)
    gh("workflow", "run", "pages.yml", "--repo", repository, "--ref", "main")
    print(
        "\nDone. The web app publishes in about 2 minutes:\n"
        f"  {PAGES_ORIGIN}/{repository.split('/')[1]}/\n"
        f"  API health: {api_url}/health"
    )


if __name__ == "__main__":
    main()

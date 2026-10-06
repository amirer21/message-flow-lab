"""Build a reproducible starter archive containing source but no credentials/history."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parent.parent
files = ["README.md", "docker-compose.yml", ".env.example", ".dockerignore", ".gitignore", "package.json", "package-lock.json", "index.html", "tsconfig.json", "vite.config.ts"]
for folder in ["backend", "frontend", "workers", "infra", "scripts", "docs"]:
    files.extend(str(path.relative_to(root)) for path in (root / folder).rglob("*") if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
files.append("public/favicon.svg")
with ZipFile(root / "public/messageflow-lab-starter.zip", "w", ZIP_DEFLATED) as archive:
    for relative in sorted(set(files)):
        archive.write(root / relative, relative.replace("\\", "/"))
print("Starter archive created (no .env, tokens, or experiment data).")

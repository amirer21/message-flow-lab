"""Generate local-only credentials without printing them or replacing an existing file."""
import secrets
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
path = root / ".env"
try:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(
            "RABBIT_USER=lab\n"
            f"RABBIT_PASSWORD={secrets.token_urlsafe(24)}\n"
            f"LAB_TOKEN={secrets.token_urlsafe(32)}\n"
            "ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,https://messageflow-lab-amire.mirohong.chatgpt.site\n"
        )
    (root / "data").mkdir(exist_ok=True)
    print(".env를 생성했습니다. 토큰은 파일에서 확인하세요. 다음: docker compose up --build")
except FileExistsError:
    print("기존 .env를 유지합니다. 다음: docker compose up --build")

# Recreate the downloadable source archive after unpacking the starter.
# The archive deliberately excludes this newly generated .env file.
subprocess.run([sys.executable, str(root / "scripts/package_lab.py")], check=True)

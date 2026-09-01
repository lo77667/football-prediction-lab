#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="artifacts"
OUT_NAME="football-prediction-lab-examples-$(date -u +%Y%m%dT%H%M%SZ).zip"

mkdir -p "$OUT_DIR"

# Use git archive if in a repo clone
if command -v git >/dev/null 2>&1 && [ -d .git ]; then
  echo "Using git archive to collect files..."
  git archive --format zip -o "$OUT_DIR/$OUT_NAME" HEAD docs/ARCHITECTURE_README.md docs/EXAMPLES || {
    echo "git archive failed (some paths may be missing). Falling back to zip.";
  }
fi

# Fallback: zip files from filesystem
if [ ! -f "$OUT_DIR/$OUT_NAME" ]; then
  echo "Creating zip from filesystem (fallback)..."
  FILES_TO_INCLUDE=()
  [ -f "docs/ARCHITECTURE_README.md" ] && FILES_TO_INCLUDE+=("docs/ARCHITECTURE_README.md")
  if [ -d "docs/EXAMPLES" ]; then
    while IFS= read -r -d $'\0' f; do
      FILES_TO_INCLUDE+=("$f")
    done < <(find docs/EXAMPLES -type f -print0)
  fi

  if [ ${#FILES_TO_INCLUDE[@]} -eq 0 ]; then
    echo "No files found to include. Exiting."
    exit 1
  fi

  if command -v zip >/dev/null 2>&1; then
    zip -r "$OUT_DIR/$OUT_NAME" "${FILES_TO_INCLUDE[@]}"
  else
    echo "zip not available; attempting with python"
    python3 - <<PY
import zipfile, sys
files = ${FILES_TO_INCLUDE}
with zipfile.ZipFile('$OUT_DIR/$OUT_NAME', 'w', zipfile.ZIP_DEFLATED) as z:
    for f in files:
        z.write(f)
print('Created zip:', '$OUT_DIR/$OUT_NAME')
PY
  fi
fi

echo "Created: $OUT_DIR/$OUT_NAME"
ls -lh "$OUT_DIR/$OUT_NAME"

# Stage and commit the artifact into this branch
if command -v git >/dev/null 2>&1 && [ -d .git ]; then
  git add "$OUT_DIR/$OUT_NAME"
  git commit -m "Add examples ZIP archive: $OUT_NAME" || echo "Nothing to commit or commit failed"
  # Push to current branch
  CUR_BRANCH=$(git rev-parse --abbrev-ref HEAD)
  echo "Pushing to branch: $CUR_BRANCH"
  git push origin "$CUR_BRANCH"
fi

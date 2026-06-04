#!/bin/bash

set -euo pipefail

# 1. 경로 및 이름 설정
SCAN_DIR=$(pwd)
CURRENT_DIR_NAME=$(basename "$SCAN_DIR")

# 결과물을 저장할 프로젝트 루트 (Git 기준 최상단, 없으면 현재 위치)
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
OUTDIR="${PROJECT_ROOT}/project_snapshot"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 결과 저장 디렉토리 생성
mkdir -p "$OUTDIR"

# 임시 통합 파일
TEMP_ALL="${OUTDIR}/.temp_snapshot_$(date +%s).tmp"
touch "$TEMP_ALL"

echo "Scanning from: $SCAN_DIR"
echo "Target filename prefix: $CURRENT_DIR_NAME"

# 2. 스냅샷 전 캐시/임시파일 삭제
echo "Cleaning cache files before snapshot..."

# 디렉토리 캐시 삭제
find "$SCAN_DIR" \
  -path "*/.git" -prune -o \
  \( \
    -name "__pycache__" -o \
    -name ".pytest_cache" -o \
    -name ".mypy_cache" -o \
    -name ".ruff_cache" -o \
    -name ".ipynb_checkpoints" -o \
    -name ".tox" -o \
    -name ".nox" -o \
    -name ".cache" \
  \) -type d -exec rm -rf {} + 2>/dev/null || true

# 파일 캐시 삭제
find "$SCAN_DIR" \
  -path "*/.git" -prune -o \
  \( \
    -name "*.pyc" -o \
    -name "*.pyo" -o \
    -name ".coverage" -o \
    -name "coverage.xml" \
  \) -type f -delete 2>/dev/null || true

# 3. 트리 구조 저장
if command -v tree >/dev/null 2>&1; then
    echo "Generating tree structure..."
    tree "$SCAN_DIR" -I "__pycache__|*.pyc|*.pyo|.DS_Store|.git|venv|.venv|.pytest_cache|.mypy_cache|.ruff_cache|.ipynb_checkpoints|.tox|.nox|.cache|project_snapshot" \
      | sed "1s|^.*$|$CURRENT_DIR_NAME (Subdir structure)|" >> "$TEMP_ALL"
else
    echo "[Tree command not found. List of files in $CURRENT_DIR_NAME:]" >> "$TEMP_ALL"
fi

# 4. 수집 대상 확장자 정의
# 필요시 여기에 확장자 추가
INCLUDE_EXPR=\
'\( -name "*.py" -o -name "*.md" -o -name "*.ipynb" -o -name "*.sh" -o -name "*.bash" -o -name "*.zsh" -o -name "*.json" -o -name "*.jsonl" -o -name "*.yaml" -o -name "*.yml" -o -name "*.toml" -o -name "*.ini" -o -name "*.cfg" -o -name "*.conf" -o -name "*.env" -o -name "*.txt" -o -name "*.sql" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" -o -name "*.css" -o -name "*.html" -o -name "*.svg" -o -name "*.mjs" \)'

# 5. 파일 내용 저장
echo "Collecting file contents..."

eval "find \"$SCAN_DIR\" \
    -path \"*/.*\" -prune -o \
    -path \"*/venv\" -prune -o \
    -path \"*/.venv\" -prune -o \
    -path \"*/node_modules\" -prune -o \
    -path \"*/__pycache__\" -prune -o \
    -path \"*/.pytest_cache\" -prune -o \
    -path \"*/.mypy_cache\" -prune -o \
    -path \"*/.ruff_cache\" -prune -o \
    -path \"*/.ipynb_checkpoints\" -prune -o \
    -path \"*/.tox\" -prune -o \
    -path \"*/.nox\" -prune -o \
    -path \"*/.cache\" -prune -o \
    -path \"*/project_snapshot\" -prune -o \
    $INCLUDE_EXPR -print0" | while IFS= read -r -d '' f; do

    RELATIVE_PATH="${f#$SCAN_DIR/}"
    printf '\n\n===== FILE: %s =====\n\n' "$RELATIVE_PATH" >> "$TEMP_ALL"
    cat "$f" >> "$TEMP_ALL"
done

# 6. 10,000줄 단위 분할 저장 (macOS 호환 로직)
TOTAL_LINES=$(wc -l < "$TEMP_ALL")
MAX_LINES=10000

# 파일명 규칙: {실행폴더명}_{시간}_part{n}.txt
FINAL_PREFIX="${CURRENT_DIR_NAME}_${TIMESTAMP}"

if [ "$TOTAL_LINES" -le "$MAX_LINES" ]; then
    mv "$TEMP_ALL" "${OUTDIR}/${FINAL_PREFIX}_part1.txt"
else
    echo "Large file detected ($TOTAL_LINES lines). Splitting..."
    split -l "$MAX_LINES" -a 3 "$TEMP_ALL" "${OUTDIR}/.split_tmp_"

    count=1
    for f in "${OUTDIR}"/.split_tmp_*; do
        mv "$f" "${OUTDIR}/${FINAL_PREFIX}_part${count}.txt"
        count=$((count + 1))
    done
    rm -f "$TEMP_ALL"
fi

echo "------------------------------------------------"
echo "Snapshot completed!"
echo "Location: $OUTDIR"
echo "Generated:"
ls "${OUTDIR}/${FINAL_PREFIX}_part"* | xargs -n 1 basename
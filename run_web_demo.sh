#!/bin/bash
# Streamlit PDF 테이블 검색 웹 데모 시작 스크립트

echo "=========================================="
echo "PDF 테이블 검색 웹 데모"
echo "=========================================="
echo ""

# 현재 디렉토리 확인
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# 필요한 패키지 설치 확인
if ! python3 -c "import streamlit" 2>/dev/null; then
    echo "Streamlit 설치 중..."
    pip3 install --user streamlit
fi

# 하이브리드 서버 확인
if ! curl -s http://localhost:5002/health > /dev/null 2>&1; then
    echo "하이브리드 서버 시작 중..."
    opendataloader-pdf-hybrid --port 5002 > /tmp/hybrid_server.log 2>&1 &
    HYBRID_PID=$!
    echo "하이브리드 서버 PID: $HYBRID_PID"
    sleep 3
    echo "하이브리드 서버 시작 완료!"
else
    echo "하이브리드 서버가 이미 실행 중입니다."
fi

echo ""
echo "=========================================="
echo "웹 데모 시작!"
echo "=========================================="
echo ""

# Streamlit 실행
python3 -m streamlit run streamlit_app.py \
    --server.port 8501 \
    --server.headless true \
    --browser.gatherUsageStats false \
    --server.maxUploadSize 500

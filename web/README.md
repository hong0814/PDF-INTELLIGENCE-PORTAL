# PDF Intelligence Portal - Frontend

React + TypeScript + Vite 기반의 PDF 문서 분석 웹 애플리케이션 프론트엔드입니다.

## 기술 스택

| 기술 | 버전 | 용도 |
|------|------|------|
| React | 19.x | UI 프레임워크 |
| TypeScript | 5.x | 타입 안전성 |
| Vite | 8.x | 빌드 도구 |
| Tailwind CSS | 4.x | 스타일링 |
| Zustand | 5.x | 상태 관리 |
| react-markdown | 10.x | 마크다운 렌더링 |
| remark-gfm | 4.x | GFM(GitHub Flavored Markdown) 지원 |
| pdf.js | 4.0 (CDN) | PDF 페이지 렌더링 |

## 실행 방법

```bash
# 의존성 설치
npm install

# 개발 서버 (HMR, localhost:8110)
npm run dev

# 프로덕션 빌드
npm run build

# 빌드 미리보기
npm run preview

# 린트 검사
npm run lint
```

개발 모드에서는 Vite 프록시가 `/api` 요청을 `http://localhost:8000`의 FastAPI 백엔드로 전달합니다.

## 프로젝트 구조

```
web/
├── src/
│   ├── main.tsx              # React 진입점
│   ├── App.tsx               # 루트 컴포넌트 (레이아웃, 검색 핸들러)
│   │
│   ├── api/
│   │   └── client.ts         # 백엔드 API 호출 함수 (fetch 기반)
│   │
│   ├── store/
│   │   └── useAppStore.ts    # Zustand 글로벌 상태 (세션, PDF, 검색결과, QA)
│   │
│   ├── types/
│   │   └── index.ts          # TypeScript 인터페이스 (TableResult, QAMessage 등)
│   │
│   └── components/
│       ├── Sidebar.tsx       # 좌측 사이드바 (PDF 업로드, 목록, 세션 관리)
│       ├── TabBar.tsx        # 상단 탭 네비게이션
│       ├── SessionHeader.tsx # 세션 정보 헤더
│       ├── MainScreen.tsx    # 메인 대시보드
│       ├── SearchBar.tsx     # 표 검색 입력 + PDF 선택 필터
│       ├── SearchResults.tsx # 표 검색 결과 래퍼
│       ├── TableCard.tsx     # 개별 표 카드 (HTML 렌더링, Q&A, CSV/HTML 다운로드)
│       ├── QAPanel.tsx       # 텍스트 검색 (문서 QA 채팅 인터페이스)
│       ├── ChatBubble.tsx    # QA 메시지 버블 + 출처 PDF 하이라이트 팝업
│       ├── DocumentViewer.tsx # PDF 페이지 뷰어 (pdf.js canvas + 테이블 오버레이)
│       ├── CreditReviewView.tsx # 기업금융심사 (이미지/차트 분석)
│       └── ProgressBar.tsx   # 진행 상태 표시줄
│
├── public/                   # 정적 파일
├── index.html                # HTML 템플릿
├── vite.config.ts            # Vite 설정 (프록시, Tailwind 플러그인)
├── package.json              # npm 의존성 및 스크립트
├── tsconfig.json             # TypeScript 설정
└── eslint.config.js          # ESLint 설정
```

## 주요 컴포넌트 설명

### App.tsx
- 애플리케이션 진입점, 전체 레이아웃 관리
- PDF 업로드, 검색 실행, 에러 처리 로직 포함
- `useEffect`에서 PDF 목록 복원 + localStorage에서 검색/QA 기록 복원

### useAppStore.ts (Zustand Store)
- **세션**: sessionId, sessionName, pdfs, totalTables, totalPages
- **검색**: results, smartResult, searchTime
- **QA**: qaMessages, documentChunksReady, tableQAs
- **선택**: selectedPdfs (검색 대상 PDF 필터링)
- **하이라이트**: highlightRegion (문서 보기에서 bounding box 강조)
- **영속성**: searchKey/qaKey/tableQaKey 별로 localStorage 자동 저장

### SearchBar.tsx
- 검색어 입력 + Smart Search 토글 + 최대 결과 수 설정
- PDF 여러 개 시 선택적 필터링 (체크박스 칩 형태)

### TableCard.tsx
- 표 HTML을 iframe으로 안전하게 렌더링 (샌드박스, XSS 방지)
- 펼치기/접기, HTML/CSV 다운로드, 마크다운 복사
- 표별 AI Q&A (추천 질문 + 자유 입력, SSE 스트리밍)

### QAPanel.tsx
- 문서 전체 기반 자연어 QA 채팅 인터페이스
- 추천 질문 칩, AI 인사말
- 답변 생성 완료 후 출처 페이지 링크 + 원본 문장 아코디언 표시

### ChatBubble.tsx
- 사용자/AI 메시지 렌더링 (HTML sanitization: `사용출처:` 라인 제거 + `**bold**` 변환)
- 출처 칩 클릭 시 `ChunkPopup` 팝업 → pdf.js로 페이지 렌더링 + 텍스트 매칭 하이라이트
- 하이라이트 로직: 6단계 폴백 매칭 (Full → Prefix → Phrase → Sliding Window → Raw Text → Character Overlap)

### DocumentViewer.tsx
- pdf.js CDN을 사용한 PDF 페이지 렌더링
- 페이지 네비게이션, 확대/축소, TXT/MD 다운로드
- `highlightRegion` 상태 감지 → 자동 페이지 이동 → bounding box 영역 반투명 하이라이트
- 테이블 오버레이 (추출된 표 위치, 클릭 시 팝업)

### CreditReviewView.tsx
- PDF 내 이미지 추출 및 페이지 컨텍스트와 함께 표시
- 이미지별 주변 텍스트, 테이블 포함 여부, 페이지 정보 제공

## 상태 관리 흐름

```
API 응답 → App.tsx handleSearch → store.setSearchResults()
                                      ↓
                              localStorage 자동 저장 (세션별 키)

페이지 로드 → useEffect → store.restoreFromStorage(sessionId)
                  ↓
           localStorage에서 해당 세션의 검색/QA 데이터 복원
```

## 개발 참고사항

- **CORS**: 개발 시 Vite 프록시가 `/api` 경로를 백엔드로 전달하므로 CORS 이슈 없음
- **pdf.js**: CDN에서 로드 (`pdfjs-dist@4.0.379`). `window.pdfjsLib`가 준비될 때까지 폴링
- **Table HTML 렌더링**: XSS 방지를 위해 `<iframe sandbox="allow-same-origin">` 사용
- **SSE 스트리밍**: Smart Search, QA, Table Q&A 모두 Server-Sent Events로 실시간 응답 처리
- **세션 간 기록 유지**: `localStorage` 키를 `pdfts_{sessionId}_search` / `qa` / `tableqas` 형식으로 분리

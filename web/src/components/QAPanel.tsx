import { useState, useRef, useEffect, useCallback } from 'react';
import type { QAMessage } from '../types';
import { useAppStore } from '../store/useAppStore';
import * as api from '../api/client';
import ChatBubble from './ChatBubble';

const RECOMMENDED_QUESTIONS = [
  '부채비율 추이는?',
  'PF대출 만기는 언제?',
  '담보가치 변동 리스크는?',
];

export default function QAPanel() {
  const qaMessages = useAppStore((s) => s.qaMessages);
  const documentChunksReady = useAppStore((s) => s.documentChunksReady);
  const totalPages = useAppStore((s) => s.totalPages);
  const pdfs = useAppStore((s) => s.pdfs);
  const sessionId = useAppStore((s) => s.sessionId);
  const addQAMessage = useAppStore((s) => s.addQAMessage);
  const updateQAMessage = useAppStore((s) => s.updateQAMessage);
  const clearQA = useAppStore((s) => s.clearQA);
  const setDocumentChunksReady = useAppStore((s) => s.setDocumentChunksReady);
  const selectedPdfs = useAppStore((s) => s.selectedPdfs);
  const setSelectedPdfs = useAppStore((s) => s.setSelectedPdfs);

  const [input, setInput] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [qaMessages]);

  const handleSend = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed) return;

      setInput('');

      const userMsgId = crypto.randomUUID();
      addQAMessage({ id: userMsgId, role: 'user', content: trimmed });

      const aiMsgId = crypto.randomUUID();
      addQAMessage({
        id: aiMsgId,
        role: 'ai',
        content: '문서를 검색하고 계산 중...',
        isLoading: true,
      });

      let accumulated = '';
      let sources: QAMessage['sources'] = [];
      try {
        await api.askDocument(trimmed, sessionId, (token) => {
          accumulated += token;
          updateQAMessage(aiMsgId, { content: accumulated });
        }, (srcs) => {
          sources = srcs;
        }, selectedPdfs);
        updateQAMessage(aiMsgId, { isLoading: false, sources });
        setDocumentChunksReady(true);
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : '오류가 발생했습니다.';
        updateQAMessage(aiMsgId, { content: errMsg, isLoading: false, sources });
      }
    },
    [sessionId, addQAMessage, updateQAMessage, setDocumentChunksReady],
  );

  const handleReset = useCallback(() => {
    clearQA();
  }, [clearQA]);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend(input);
      }
    },
    [handleSend, input],
  );

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto">
      {/* Header */}
      <div className="px-5 py-3 border-b bg-surface-elevated flex items-center justify-between">
        <div className="flex items-center gap-2">
          <svg className="w-4 h-4 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
          </svg>
          <span className="text-sm font-semibold">텍스트 검색</span>
          {(documentChunksReady || totalPages > 0 || pdfs.length > 0) && (
            <span className="text-xs px-2 py-0.5 bg-success/10 text-success rounded-full flex items-center gap-1">
              <span className="w-2 h-2 bg-success rounded-full" />
              문서 이해 완료
            </span>
          )}
        </div>
        <button onClick={handleReset} className="text-xs border border-border rounded-lg px-3 py-1.5 text-text-muted hover:bg-surface transition-colors">
          대화 초기화
        </button>
      </div>

      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 space-y-5 bg-surface">
        {/* Recommended questions chips */}
        <div className="flex flex-wrap gap-2 mb-2">
          {RECOMMENDED_QUESTIONS.map((q) => (
            <button key={q} onClick={() => handleSend(q)} className="text-xs px-3 py-1.5 rounded-full border border-border bg-surface-elevated hover:border-primary hover:text-primary transition-colors">
              {q}
            </button>
          ))}
        </div>

        {/* AI greeting when no messages and docs exist */}
        {qaMessages.length === 0 && pdfs.length > 0 && (
          <ChatBubble
            message={{
              id: 'greeting',
              role: 'ai',
              content: `안녕하세요. 문서를 모두 읽었습니다. 총 ${totalPages}페이지를 분석하였습니다.<br><br>궁금한 내용을 자유롭게 질문해 주세요.`,
            }}
          />
        )}

        {/* Messages */}
        {qaMessages.map((msg) => (
          <ChatBubble key={msg.id} message={msg} />
        ))}
      </div>

      {/* Input area */}
      <div className="p-4 border-t bg-white">
        {pdfs.length > 1 && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {pdfs.map((pdf) => {
              const checked = selectedPdfs.includes(pdf.name);
              return (
                <label
                  key={pdf.name}
                  className={`flex items-center gap-1 px-2.5 py-1 text-xs rounded-full cursor-pointer border transition-colors ${
                    checked
                      ? 'bg-primary/10 border-primary/30 text-primary'
                      : 'bg-gray-50 border-border text-text-muted hover:text-text-secondary hover:border-primary/20'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => {
                      if (checked) {
                        setSelectedPdfs(selectedPdfs.filter((n) => n !== pdf.name));
                      } else {
                        setSelectedPdfs([...selectedPdfs, pdf.name]);
                      }
                    }}
                    className="sr-only"
                  />
                  <span className="truncate max-w-[120px]">{pdf.name}</span>
                </label>
              );
            })}
          </div>
        )}
        <div className="flex items-end gap-2">
          <div className="flex-1 relative">
            <textarea
              rows={1}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="문서에 대해 궁금한 점을 질문하세요..."
              className="w-full resize-none rounded-xl border border-border px-4 py-3 pr-10 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary/20"
            />
          </div>
          <button onClick={() => handleSend(input)} className="w-10 h-10 rounded-xl bg-primary hover:bg-primary-hover text-white flex items-center justify-center shrink-0">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
            </svg>
          </button>
        </div>
        <p className="text-xs text-text-muted mt-2 text-center">
          AI 답변은 문서 기반이지만, 최종 결정은 심사역의 검토가 필요합니다.
        </p>
      </div>
    </div>
  );
}

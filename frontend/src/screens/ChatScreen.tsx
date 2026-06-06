import { useEffect, useMemo, useState } from "react";
import type { ApiClient } from "@/api/client";
import { AnswerStreamClient } from "@/api/sse";
import type { DocumentId, TocEntry } from "@/api/types";
import { ChatStream } from "@/components/ChatStream";
import { ChatComposer } from "@/components/ChatComposer";
import { EmptyState } from "@/components/EmptyState";
import { useAnswerStream } from "@/hooks/useAnswerStream";
import { apiBaseUrl, getSessionToken } from "@/config";

interface ChatScreenProps {
  client: ApiClient;
  documentId: DocumentId;
  documentTitle: string;
}

/**
 * Chat screen (FR-007, FR-008, FR-011, FR-012, FR-018). Streams cited answers
 * for the open document via `POST /v1/answer` and renders each turn with the
 * ConfidenceMeter, CitationCards, ExplainabilityPanel, and FallbackBanner. The
 * document's TOC is fetched once so the ExplainabilityPanel can join routing
 * section ids to section titles/pages (GRC-001).
 *
 * @param client - The typed API client (for the one-time TOC fetch).
 * @param documentId - The document to ask questions about.
 * @param documentTitle - The document title (composer placeholder + header).
 */
export function ChatScreen({ client, documentId, documentTitle }: ChatScreenProps): JSX.Element {
  const [toc, setToc] = useState<TocEntry[]>([]);

  const streamClient = useMemo(
    () => new AnswerStreamClient({ baseUrl: apiBaseUrl(), getToken: getSessionToken }),
    [],
  );
  const { turns, pending, ask } = useAnswerStream(streamClient);

  useEffect(() => {
    let active = true;
    void client
      .getDocumentToc(documentId)
      .then((response) => {
        if (active) {
          setToc(response.toc);
        }
      })
      .catch(() => {
        if (active) {
          setToc([]);
        }
      });
    return () => {
      active = false;
    };
  }, [client, documentId]);

  return (
    <main id="main-content" className="mx-auto flex h-full max-w-chat flex-col">
      <div className="flex-1 overflow-y-auto px-md py-xl">
        {turns.length === 0 ? (
          <EmptyState
            heading={`Ask about ${documentTitle}`}
            body="Type a question below. The router will scope retrieval to the most relevant sections and stream a cited answer."
          />
        ) : (
          <ChatStream turns={turns} toc={toc} />
        )}
      </div>
      <ChatComposer
        documentTitle={documentTitle}
        disabled={pending}
        onSubmit={(query) => ask(documentId, query)}
      />
    </main>
  );
}

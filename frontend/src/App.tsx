import { useMemo, useState } from "react";
import { ApiClient } from "@/api/client";
import type { Document } from "@/api/types";
import { AppHeader } from "@/components/AppHeader";
import { UploadLibraryScreen } from "@/screens/UploadLibraryScreen";
import { DocumentViewScreen } from "@/screens/DocumentViewScreen";
import { ChatScreen } from "@/screens/ChatScreen";
import { apiBaseUrl, getSessionToken } from "@/config";

/** Which top-level screen is active. */
type View =
  | { name: "library" }
  | { name: "document"; doc: Document }
  | { name: "chat"; doc: Document };

/** Resolve a document's display title, falling back to its id. */
function titleOf(doc: Document): string {
  return doc.title ?? doc.doc_id;
}

/**
 * Application shell for the personal-tool SPA. Owns lightweight view state
 * (library -> document -> chat) and constructs a single {@link ApiClient} bound
 * to the configured base URL and the session JWT provider (ADR-7). Routing is
 * intentionally state-based - the SPA has no deep-linking requirement in MVP.
 */
export function App(): JSX.Element {
  const [view, setView] = useState<View>({ name: "library" });

  const client = useMemo(
    () => new ApiClient({ baseUrl: apiBaseUrl(), getToken: getSessionToken }),
    [],
  );

  const headerTitle = view.name === "library" ? undefined : titleOf(view.doc);

  return (
    <div className="min-h-screen bg-surface">
      <AppHeader {...(headerTitle === undefined ? {} : { documentTitle: headerTitle })} />
      {view.name === "library" ? (
        <UploadLibraryScreen
          client={client}
          onOpenDocument={(doc) => setView({ name: "document", doc })}
        />
      ) : null}
      {view.name === "document" ? (
        <DocumentViewScreen
          client={client}
          documentId={view.doc.doc_id}
          documentTitle={titleOf(view.doc)}
          onStartChat={() => setView({ name: "chat", doc: view.doc })}
        />
      ) : null}
      {view.name === "chat" ? (
        <ChatScreen
          client={client}
          documentId={view.doc.doc_id}
          documentTitle={titleOf(view.doc)}
        />
      ) : null}
    </div>
  );
}

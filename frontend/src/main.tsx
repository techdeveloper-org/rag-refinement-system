import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "@/App";
import "@/styles/index.css";

/**
 * SPA entry point. Mounts the {@link App} into the `#root` element declared in
 * index.html. Throws early if the mount node is absent so a misconfigured host
 * page fails loudly rather than rendering nothing.
 */
const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("Root element #root not found in index.html");
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

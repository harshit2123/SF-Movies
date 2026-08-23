import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import "./styles/tokens.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The dataset is a batch snapshot (ADR-0003), so refetching whenever the
      // window regains focus would issue requests that cannot return new data.
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);

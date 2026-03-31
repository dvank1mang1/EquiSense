import type { AppProps } from "next/app";
import { SWRConfig } from "swr";
import { getApiError } from "@/lib/api";
import "../styles/globals.css";

export default function App({ Component, pageProps }: AppProps) {
  return (
    <SWRConfig
      value={{
        onError: (err) => {
          const ae = getApiError(err);
          if (ae) {
            console.warn(`[SWR] ${ae.code}: ${ae.message} (request_id=${ae.request_id})`);
          }
        },
        shouldRetryOnError: false,
      }}
    >
      <Component {...pageProps} />
    </SWRConfig>
  );
}

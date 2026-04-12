import type { AppProps } from "next/app";
import { Inter } from "next/font/google";
import { SWRConfig } from "swr";
import { getApiError } from "@/lib/api";
import "../styles/globals.css";

const inter = Inter({
  subsets: ["latin", "cyrillic"],
  display: "swap",
  variable: "--font-sans",
});

export default function App({ Component, pageProps }: AppProps) {
  return (
    <div className={`${inter.variable} ${inter.className} min-h-screen`}>
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
    </div>
  );
}

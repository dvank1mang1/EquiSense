import { describe, expect, it } from "vitest";
import { AxiosError } from "axios";
import { getClientError, toApiClientError } from "./api";

function axiosErr(partial: Partial<AxiosError> & { response?: AxiosError["response"] }): AxiosError {
  const err = new AxiosError(
    partial.message ?? "fail",
    partial.code,
    partial.config,
    partial.request,
    partial.response
  );
  return err;
}

describe("toApiClientError", () => {
  it("classifies parsed API errors", () => {
    const err = axiosErr({
      response: {
        status: 404,
        data: { error: { code: "http_404", message: "Missing", request_id: "r1" } },
      } as AxiosError["response"],
    });
    const c = toApiClientError(err);
    expect(c.kind).toBe("api");
    expect(c.code).toBe("http_404");
    expect(c.requestId).toBe("r1");
    expect(c.retryable).toBe(false);
  });

  it("marks 5xx API errors as retryable", () => {
    const err = axiosErr({
      response: {
        status: 503,
        data: { error: { code: "http_503", message: "Down", request_id: "r2" } },
      } as AxiosError["response"],
    });
    expect(toApiClientError(err).retryable).toBe(true);
  });

  it("classifies timeout and network", () => {
    expect(toApiClientError(axiosErr({ code: "ECONNABORTED" })).kind).toBe("timeout");
    expect(toApiClientError(axiosErr({ code: "ERR_CANCELED" })).kind).toBe("cancelled");
    expect(toApiClientError(axiosErr({ message: "x" })).kind).toBe("network");
  });

  it("handles non-axios unknown", () => {
    const c = toApiClientError(new Error("boom"));
    expect(c.kind).toBe("unknown");
    expect(c.retryable).toBe(false);
  });
});

describe("getClientError", () => {
  it("returns client error attached by interceptor", () => {
    const err = axiosErr({
      response: { status: 400, data: {} } as AxiosError["response"],
    });
    (err as AxiosError & { clientError?: ReturnType<typeof toApiClientError> }).clientError =
      toApiClientError(err);
    expect(getClientError(err)?.kind).toBeDefined();
  });
});

export type ProductPageOverviewState =
  | "ready"
  | "unauthorized"
  | "limit_reached"
  | "indexing";

interface ProductPageOverviewStateInput {
  overviewOk: boolean;
  overviewStatus: number;
  explainerStatus: number;
  topicsStatus: number;
}

const USAGE_LIMIT_HTTP_STATUS = 429;
const OVERVIEW_UNAUTHORIZED_HTTP_STATUS = 401;

export function deriveProductPageOverviewState({
  overviewOk,
  overviewStatus,
  explainerStatus,
  topicsStatus,
}: ProductPageOverviewStateInput): ProductPageOverviewState {
  if (overviewOk) {
    return "ready";
  }

  if (overviewStatus === OVERVIEW_UNAUTHORIZED_HTTP_STATUS) {
    return "unauthorized";
  }

  const hasUsageLimitResponse = [
    overviewStatus,
    explainerStatus,
    topicsStatus,
  ].some((status) => status === USAGE_LIMIT_HTTP_STATUS);

  if (hasUsageLimitResponse) {
    return "limit_reached";
  }

  return "indexing";
}

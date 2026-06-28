import {
  extractIndexationErrorCode,
  isThinEvidenceError,
} from "@/lib/pipeline-errors";

export type ProductPageOverviewState =
  | "ready"
  | "unauthorized"
  | "limit_reached"
  | "server_error"
  | "thin_evidence"
  | "indexing";

interface ProductPageOverviewStateInput {
  overviewOk: boolean;
  overviewStatus: number;
  explainerStatus: number;
  topicsStatus: number;
  productStatus?: number;
  documentsStatus?: number;
  overviewPayload?: unknown;
}

const OVERVIEW_UNAUTHORIZED_HTTP_STATUS = 401;
/** 429 Too Many Requests — monthly/preview quota exhausted. */
const USAGE_LIMIT_HTTP_STATUS = 429;

function isUsageLimitStatus(status: number): boolean {
  return status === USAGE_LIMIT_HTTP_STATUS;
}

function isServerErrorStatus(status: number): boolean {
  return status >= 500;
}

export function deriveProductPageOverviewState({
  overviewOk,
  overviewStatus,
  explainerStatus,
  topicsStatus,
  productStatus,
  documentsStatus,
  overviewPayload,
}: ProductPageOverviewStateInput): ProductPageOverviewState {
  if (overviewOk) {
    return "ready";
  }

  if (overviewStatus === OVERVIEW_UNAUTHORIZED_HTTP_STATUS) {
    return "unauthorized";
  }

  if (
    overviewPayload !== undefined &&
    isThinEvidenceError(extractIndexationErrorCode(overviewPayload))
  ) {
    return "thin_evidence";
  }

  const statuses = [
    overviewStatus,
    explainerStatus,
    topicsStatus,
    productStatus,
    documentsStatus,
  ].filter((status): status is number => status !== undefined);

  if (statuses.some(isUsageLimitStatus)) {
    return "limit_reached";
  }

  if (statuses.some(isServerErrorStatus)) {
    return "server_error";
  }

  return "indexing";
}

export function isProductNotFound(productStatus: number): boolean {
  return productStatus === 404;
}

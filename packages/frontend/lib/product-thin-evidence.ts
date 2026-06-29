import { isThinEvidenceError } from "@/lib/pipeline-errors";
import type { Product } from "@/types";

export function productHasThinEvidence(
  product: Product | null | undefined,
): boolean {
  return (
    product?.thin_evidence === true ||
    isThinEvidenceError(product?.indexation_error)
  );
}

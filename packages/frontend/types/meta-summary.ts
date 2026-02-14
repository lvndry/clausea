export interface MetaSummary {
  summary: string;
  scores: Record<string, { score: number; justification: string }>;
  keypoints: string[];
}

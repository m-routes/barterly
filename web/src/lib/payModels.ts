export type PayModel = "volunteer" | "barter" | "hybrid" | "paid";

export const PAY_MODELS: Record<PayModel, { label: string; summary: string }> = {
  volunteer: { label: "Volunteer", summary: "Work for stay" },
  barter: { label: "Barter", summary: "Content for stay" },
  hybrid: { label: "Hybrid", summary: "Stay plus stipend" },
  paid: { label: "Paid", summary: "Paid role" },
};

export function describePayModel(model: PayModel): string {
  const { label, summary } = PAY_MODELS[model];
  return `${label}: ${summary}`;
}

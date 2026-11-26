/** Paise as rupees: 249900 → "₹2,499". Whole rupees lose the ".00". */
export function rupees(paise: number): string {
  const value = paise / 100;
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(value);
}

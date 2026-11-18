import { redirect } from "next/navigation";

/** Payments became Billing. */
export default function PaymentsPage() {
  redirect("/console/billing");
}

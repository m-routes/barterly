import type { Metadata } from "next";

import { LegalPage } from "@/components/legal/LegalPage";

import { GrievanceOfficer } from "./GrievanceOfficer";

export const metadata: Metadata = { title: "Grievance Officer · Barterly" };

export default function GrievancePage() {
  return (
    <LegalPage title="Grievance Officer">
      <p>
        If you have a complaint about Barterly, about how we handle your personal data, or about
        content on the platform, write to our Grievance Officer. We acknowledge every complaint and
        tell you what we did about it.
      </p>
      <GrievanceOfficer />
      <h2>What to include</h2>
      <ul>
        <li>The mobile number on your account (never your OTP).</li>
        <li>What happened, and links or booking references if you have them.</li>
        <li>What you would like us to do.</li>
      </ul>
      <p>
        If we don&rsquo;t resolve a complaint about your personal data, you can approach the Data
        Protection Board of India.
      </p>
    </LegalPage>
  );
}

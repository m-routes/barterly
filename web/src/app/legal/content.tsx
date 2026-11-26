import Link from "next/link";

import type { LegalSlug } from "@/lib/legal/documents";

/*
 * DRAFT TEXT FOR LAWYER REVIEW. Not legal advice and not in force. Placeholders in
 * [square brackets] are for the company's details. Questions for the lawyer are listed
 * in docs/privacy.md under "Open legal questions".
 */

function Terms() {
  return (
    <>
      <h2>1. Who we are</h2>
      <p>
        Barterly is operated by [Company name], a company registered in India at [registered
        address] (&ldquo;Barterly&rdquo;, &ldquo;we&rdquo;). Barterly is a marketplace: we connect
        hosts (hostels, homestays, cafés, camps and tour operators) with talent (artists, creators
        and skilled travellers) who exchange work for stays, meals or a stipend.
      </p>
      <h2>2. Who can use Barterly</h2>
      <p>
        You must be at least 18 years old and able to enter a binding contract under Indian law. If
        we learn that an account belongs to someone under 18, we suspend it and delete its data,
        keeping only what the law requires.
      </p>
      <h2>3. Your account</h2>
      <p>
        You sign in with your mobile number and a one-time code. Keep your phone secure; you are
        responsible for what is done with your account. Tell us at once if you think someone else
        has used it.
      </p>
      <h2>4. Gigs, offers and agreements</h2>
      <p>
        Hosts post gigs; talent apply. When both sides accept an offer, each signs an agreement that
        sets out the work, the stay and the dates. That agreement is between the host and the
        talent. Barterly is not an employer or an agent of either side.
      </p>
      <h2>5. Stipends and payments</h2>
      <p>
        For paid and hybrid gigs, the host pays the stipend into escrow through our payment partner
        before the stay. It is released to the talent when the work is accepted, or automatically
        after the review period, less our commission, GST and any TDS the law requires. The{" "}
        <Link href="/legal/refunds">refund policy</Link> explains cancellations.
      </p>
      <h2>6. Your content</h2>
      <p>
        You keep the rights to what you upload. You give Barterly a licence to host and show it to
        run the service. Deliverables made for a host are licensed to that host as the agreement
        says.
      </p>
      <h2>7. Rules</h2>
      <p>
        Follow the <Link href="/legal/community-rules">community rules</Link>. We may remove
        content, issue strikes, suspend or close accounts that break them, and you can appeal.
      </p>
      <h2>8. Liability</h2>
      <p>
        [To be drafted by counsel: limitation of liability, indemnity, intermediary status under
        section 79 of the IT Act, 2000, force majeure.]
      </p>
      <h2>9. Complaints and disputes</h2>
      <p>
        Contact our <Link href="/grievance">Grievance Officer</Link>. [Governing law, jurisdiction
        and dispute resolution to be drafted by counsel.]
      </p>
      <h2>10. Changes</h2>
      <p>
        When these terms change in a way that matters, we tell you and ask you to accept the new
        version before you go on using Barterly.
      </p>
    </>
  );
}

function Privacy() {
  return (
    <>
      <h2>1. Who is responsible</h2>
      <p>
        [Company name] is the Data Fiduciary for the personal data described here under the Digital
        Personal Data Protection Act, 2023 (DPDP Act). Questions and complaints go to our{" "}
        <Link href="/grievance">Grievance Officer</Link>.
      </p>
      <h2>2. What we collect and why</h2>
      <ul>
        <li>
          <strong>Account:</strong> your mobile number (to sign you in) and optionally your email.
        </li>
        <li>
          <strong>Profile:</strong> name, bio, skills, languages, city, date of birth (talent, to
          confirm you are 18 or older), emergency contact (shared with your host only during a
          stay), business details (hosts).
        </li>
        <li>
          <strong>Verification:</strong> the result of an ID and selfie check run by our KYC
          provider. We keep only the outcome and the last four characters of the ID number; the
          images and full numbers stay with the provider.
        </li>
        <li>
          <strong>Bookings and money:</strong> applications, offers, signed agreements, check-ins,
          deliverables, reviews, payments and payouts. Bank details are held by our payment partner;
          we keep a masked reference.
        </li>
        <li>
          <strong>Messages:</strong> chats between hosts and talent, to run bookings and keep people
          safe.
        </li>
      </ul>
      <h2 id="location">3. Location (only with your consent)</h2>
      <p>
        If you allow it, the app records where you are when you open your check-in pass, to note how
        far you were from the property. You can withdraw this consent at any time in your privacy
        settings; check-in still works without it. Location records are deleted after 30 days.
      </p>
      <h2 id="social">4. Social accounts (only with your consent)</h2>
      <p>
        If you allow it, we read public numbers (views, likes, comments) for posts you hand in as
        deliverables, and check the handle you give us. Withdraw it in your privacy settings and we
        stop.
      </p>
      <h2 id="marketing">5. Marketing (only with your consent)</h2>
      <p>
        We send offers and news only if you ask for them, and you can stop them at any time. Service
        messages about your bookings and payments are not marketing.
      </p>
      <h2>6. Who we share it with</h2>
      <p>
        The other side of a booking (what they need for the stay), our processors (hosting, SMS and
        email, payments, KYC, e-signatures), and authorities when the law requires it. We do not
        sell personal data.
      </p>
      <h2>7. How long we keep it</h2>
      <p>
        Only as long as we need it. Payment and tax records are kept for eight years and signed
        agreements for the length of the agreement plus three years, because the law requires it.
        When you delete your account, those records are kept with your personal details removed.
        Details for each kind of data are in our retention schedule [link once published].
      </p>
      <h2>8. Your rights</h2>
      <p>
        You can see and download your data, correct it, withdraw consent and delete your account
        from your privacy settings. Withdrawing consent is as easy as giving it. You can nominate
        someone to exercise your rights if you die or cannot act [process to be confirmed]. If we
        don&rsquo;t resolve a complaint, you can approach the Data Protection Board of India.
      </p>
      <h2>9. Children</h2>
      <p>
        Barterly is only for people aged 18 and over. We do not knowingly process children&rsquo;s
        data.
      </p>
      <h2>10. Security and breaches</h2>
      <p>
        We protect data with encryption, access controls and logging. If a breach affects you, we
        tell you and the Data Protection Board as the law requires.
      </p>
    </>
  );
}

function CommunityRules() {
  return (
    <>
      <h2>Be honest</h2>
      <p>
        Describe gigs, stays and skills as they are. Use your own identity. One account per person.
      </p>
      <h2>Be safe and respectful</h2>
      <ul>
        <li>No harassment, discrimination, threats or sexual content directed at anyone.</li>
        <li>Hosts provide the stay, meals and working conditions the agreement promises.</li>
        <li>Talent turn up as agreed and deliver the agreed work.</li>
        <li>No one under 18 may be hosted or join, whatever their role.</li>
      </ul>
      <h2>Keep it on Barterly until you&rsquo;re booked</h2>
      <p>
        Don&rsquo;t share phone numbers or take payment off the platform before a booking is
        confirmed; escrow and our safety tools only protect bookings made here.
      </p>
      <h2>Follow the law</h2>
      <p>
        No illegal work, no unpaid labour disguised as a barter, and disclose paid partnerships in
        content as the ASCI guidelines require.
      </p>
      <h2>What happens if rules are broken</h2>
      <p>
        We may remove content, issue strikes, suspend or ban accounts. You can appeal any decision.
      </p>
    </>
  );
}

function Refunds() {
  return (
    <>
      <h2>Stipends held in escrow</h2>
      <ul>
        <li>Cancelled before the stay starts: the host is refunded in full, less gateway fees.</li>
        <li>
          Talent doesn&rsquo;t turn up: the host is refunded in full once the no-show is confirmed.
        </li>
        <li>
          A dispute about the work: the stipend stays in escrow until Barterly decides, which may be
          a full refund, a full release or a split.
        </li>
      </ul>
      <p>
        Refunds go back to the original payment method within [5–7] working days of the decision.
      </p>
      <h2>Plans</h2>
      <p>
        Plan fees are charged in advance and are not refunded for a part of a billing period, unless
        the law requires it. You can cancel at any time; the plan runs to the end of the paid
        period.
      </p>
      <h2>How to ask</h2>
      <p>
        Contact support from the booking, or our <Link href="/grievance">Grievance Officer</Link>.
      </p>
    </>
  );
}

export const LEGAL_CONTENT: Record<LegalSlug, () => React.ReactNode> = {
  terms: Terms,
  privacy: Privacy,
  "community-rules": CommunityRules,
  refunds: Refunds,
};

/** The vendor console's sections, in sidebar order. */
export type ConsoleSection = {
  href: string;
  label: string;
  /** Empty-state copy until the section is built. */
  empty: { title: string; description: string };
};

export const CONSOLE_SECTIONS: readonly ConsoleSection[] = [
  {
    href: "/console",
    label: "Dashboard",
    empty: {
      title: "Nothing to show yet",
      description:
        "Once you post gigs and talent apply, your bookings, applications and messages will show up here.",
    },
  },
  {
    href: "/console/gigs",
    label: "Gigs",
    empty: {
      title: "No gigs yet",
      description:
        "Gigs describe the help you need and what you offer in return. Post your first one.",
    },
  },
  {
    href: "/console/applicants",
    label: "Applicants",
    empty: {
      title: "No applicants yet",
      description: "When talent apply to your gigs, you'll review and shortlist them here.",
    },
  },
  {
    href: "/console/properties",
    label: "Properties",
    empty: {
      title: "No properties yet",
      description: "Add the place talent will stay and work. Each gig belongs to a property.",
    },
  },
  {
    href: "/console/verification",
    label: "Verification",
    empty: {
      title: "Not verified yet",
      description: "Verify your ID and your property to get badges on your gigs.",
    },
  },
  {
    href: "/console/talent",
    label: "Talent search",
    empty: {
      title: "Talent search is coming soon",
      description: "You'll be able to find artists, creators and more by skill, language and city.",
    },
  },
  {
    href: "/console/agreements",
    label: "Agreements",
    empty: {
      title: "No agreements yet",
      description:
        "Agreements set out the work, the stay and the dates once you and the talent say yes.",
    },
  },
  {
    href: "/console/payments",
    label: "Payments",
    empty: {
      title: "No payments yet",
      description: "Stipends and paid gigs will be tracked here, with receipts for each payment.",
    },
  },
  {
    href: "/console/analytics",
    label: "Analytics",
    empty: {
      title: "No data yet",
      description: "See how your gigs perform: views, applications and completed stays.",
    },
  },
];

export function sectionFor(href: string): ConsoleSection {
  const section = CONSOLE_SECTIONS.find((s) => s.href === href);
  if (!section) throw new Error(`Unknown console section: ${href}`);
  return section;
}

/** The section a pathname belongs to (the dashboard only matches exactly). */
export function activeSection(pathname: string): ConsoleSection | undefined {
  return CONSOLE_SECTIONS.find((s) =>
    s.href === "/console"
      ? pathname === "/console"
      : pathname === s.href || pathname.startsWith(`${s.href}/`),
  );
}

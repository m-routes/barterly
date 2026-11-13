import Link from "next/link";

import { Logo } from "@/components/Logo";
import { PAY_MODELS, type PayModel } from "@/lib/payModels";

const STEPS = [
  {
    title: "Tell us about your place",
    text: "Hostel, homestay, café, camp or tour: set up your business profile in a few minutes.",
  },
  {
    title: "Post what you need",
    text: "A mural, a menu refresh, reels for your stay, help at the front desk.",
  },
  {
    title: "Pick your talent",
    text: "Review applicants, agree the terms, and host them for the stay.",
  },
];

export default function Home() {
  return (
    <div className="landing">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <header className="landing__header">
        <Logo />
        <Link href="/login" className="button button--secondary">
          Sign in
        </Link>
      </header>

      <main id="main">
        <section className="hero" aria-labelledby="hero-title">
          <p className="hero__eyebrow">Barterly vendor console</p>
          <h1 id="hero-title" className="hero__title">
            Find talent for your stay, café or tour
          </h1>
          <p className="hero__lead">
            Barterly connects travel and hospitality businesses across India with artists, creators
            and skilled travellers who trade their work for stays, meals or pay.
          </p>
          <div className="hero__actions">
            <Link href="/login" className="button button--primary">
              Get started
            </Link>
            <a href="#how-it-works" className="button button--ghost">
              How it works
            </a>
          </div>
        </section>

        <section id="how-it-works" className="landing__section" aria-labelledby="how-title">
          <h2 id="how-title" className="section-title">
            How it works
          </h2>
          <ol className="steps">
            {STEPS.map((step, index) => (
              <li key={step.title} className="steps__item">
                <span className="steps__number" aria-hidden="true">
                  {index + 1}
                </span>
                <h3 className="steps__title">{step.title}</h3>
                <p className="steps__text">{step.text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="landing__section" aria-labelledby="pay-title">
          <h2 id="pay-title" className="section-title">
            Ways to work together
          </h2>
          <ul className="pay-models" aria-label="Pay models">
            {(Object.keys(PAY_MODELS) as PayModel[]).map((model) => (
              <li key={model} className="pay-models__item">
                <strong className="pay-models__label">{PAY_MODELS[model].label}</strong>
                <span>{PAY_MODELS[model].summary}</span>
              </li>
            ))}
          </ul>
        </section>
      </main>

      <footer className="landing__footer">
        <p>© Barterly. Made for travel and hospitality in India.</p>
      </footer>
    </div>
  );
}

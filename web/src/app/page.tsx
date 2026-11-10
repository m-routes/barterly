import { PAY_MODELS, type PayModel } from "@/lib/payModels";

export default function Home() {
  return (
    <main className="home">
      <h1>Barterly vendor console</h1>
      <p>Work exchange for travel and hospitality in India.</p>
      <ul aria-label="Pay models">
        {(Object.keys(PAY_MODELS) as PayModel[]).map((model) => (
          <li key={model}>
            <strong>{PAY_MODELS[model].label}</strong> — {PAY_MODELS[model].summary}
          </li>
        ))}
      </ul>
    </main>
  );
}

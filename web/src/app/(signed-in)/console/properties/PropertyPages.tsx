"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import { useLoad } from "@/lib/hooks/useLoad";

import { PropertyForm } from "./PropertyForm";
import { PropertyPhotos } from "./PropertyPhotos";
import { PropertyVerification } from "./PropertyVerification";

function BackLink() {
  return (
    <Link href="/console/properties" className="back-link">
      All properties
    </Link>
  );
}

export function NewProperty() {
  const router = useRouter();
  return (
    <div className="page page--narrow">
      <header className="page__header">
        <BackLink />
        <h1 className="page__title">Add a property</h1>
        <p className="page__lead">
          Save the details and the map pin first. Then add photos and ask us to verify it.
        </p>
      </header>
      <PropertyForm
        initial={null}
        onSaved={(property) => router.replace(`/console/properties/${property.id}`)}
      />
    </div>
  );
}

export function EditProperty() {
  const { propertyId } = useParams<{ propertyId: string }>();
  const { state, reload, setData } = useLoad(
    () =>
      unwrap(
        api.GET("/api/v1/properties/{property_id}/", {
          params: { path: { property_id: propertyId } },
        }),
      ),
    propertyId,
  );

  if (state.status === "loading") return <LoadingState label="Loading the property…" />;
  if (state.status === "error") {
    return (
      <div className="page">
        <ErrorState
          title="We couldn't load this property"
          description={describeError(state.error)}
          retry={() => void reload()}
          action={{ label: "All properties", href: "/console/properties" }}
        />
      </div>
    );
  }
  const property = state.data;
  return (
    <div className="page page--narrow">
      <header className="page__header">
        <BackLink />
        <h1 className="page__title">{property.name}</h1>
      </header>
      <div className="stack">
        <PropertyVerification
          property={property}
          onStatus={(status) => setData((p) => ({ ...p, verification_status: status }))}
        />
        <PropertyPhotos
          property={property}
          onChange={(photos) => setData((p) => ({ ...p, photos }))}
        />
        <PropertyForm initial={property} onSaved={(saved) => setData(() => saved)} />
      </div>
    </div>
  );
}

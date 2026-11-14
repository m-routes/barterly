import type { NextRequest } from "next/server";

import { handleApiRequest } from "@/lib/server/bff";
import { apiUrl } from "@/lib/server/env";

// Every /api/v1/* call from the browser goes through here to the Django API.
function handler(request: NextRequest) {
  return handleApiRequest(request, apiUrl());
}

export { handler as DELETE, handler as GET, handler as PATCH, handler as POST, handler as PUT };

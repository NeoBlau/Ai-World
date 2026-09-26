import { Suspense } from "react";

import { WorldScreen } from "@/features/world/WorldScreen";

export const metadata = { title: "World" };

export default function WorldPage() {
  return (
    <Suspense>
      <WorldScreen />
    </Suspense>
  );
}

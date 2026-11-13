import { createFileRoute } from "@tanstack/react-router";
import { AuthScreen } from "@/components/auth-screen";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "kupé — Sign in" },
      { name: "description", content: "Sign in to kupé with your email or Google." },
      { property: "og:title", content: "kupé — Sign in" },
      { property: "og:description", content: "Sign in to kupé with your email or Google." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: AuthScreen,
});

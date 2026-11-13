import { createFileRoute } from "@tanstack/react-router";
import { AuthScreen } from "@/components/auth-screen";

export const Route = createFileRoute("/signup")({
  head: () => ({ meta: [
    { title: "kupé — Create account" },
    { name: "description", content: "Create your kupé account with your email or Google." },
    { property: "og:title", content: "kupé — Create account" },
    { property: "og:description", content: "Create your kupé account with your email or Google." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary" },
  ] }),
  component: () => <AuthScreen signup />,
});
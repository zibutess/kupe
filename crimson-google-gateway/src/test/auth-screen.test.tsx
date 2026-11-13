import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthScreen } from "@/components/auth-screen";

vi.mock("@tanstack/react-router", () => ({ Link: ({ to, children }: { to: string; children: React.ReactNode }) => <a href={to}>{children}</a> }));
afterEach(cleanup);

describe("Terms agreement", () => {
  it("requires agreement before email sign-in", () => {
    render(<AuthScreen />);
    const submit = screen.getByRole("button", { name: "Sign in" });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    expect(submit).toBeEnabled();
  });

  it("requires agreement before Google sign-in", () => {
    render(<AuthScreen />);
    const google = screen.getByRole("button", { name: "Continue with Google" });
    expect(google).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    expect(google).toBeEnabled();
  });

  it("requires agreement before registration", () => {
    render(<AuthScreen signup />);
    const submit = screen.getByRole("button", { name: "Create account" });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    expect(submit).toBeEnabled();
  });
});
import { useState, type FormEvent } from "react";
import { Link } from "@tanstack/react-router";
import { ArrowRight, Eye, EyeOff, LockKeyhole, Mail, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import train from "@/assets/train-ink.jpg";

function GoogleMark() {
  return <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24"><path className="google-blue" d="M23.49 12.27c0-.79-.07-1.54-.19-2.27H12v4.51h6.47c-.29 1.48-1.14 2.73-2.4 3.58v3h3.86c2.26-2.09 3.56-5.17 3.56-8.82z"/><path className="google-green" d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.86-3c-1.08.72-2.45 1.16-4.07 1.16-3.13 0-5.78-2.11-6.73-4.96H1.29v3.09C3.26 21.3 7.31 24 12 24z"/><path className="google-yellow" d="M5.27 14.29c-.25-.72-.38-1.49-.38-2.29s.14-1.57.38-2.29V6.62H1.29C.47 8.24 0 10.06 0 12s.47 3.76 1.29 5.38l3.98-3.09z"/><path className="google-red" d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.31 0 3.26 2.7 1.29 6.62l3.98 3.09c.95-2.85 3.6-4.96 6.73-4.96z"/></svg>;
}

export function AuthScreen({ signup = false }: { signup?: boolean }) {
  const [visible, setVisible] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [note, setNote] = useState("");
  const [legal, setLegal] = useState<"terms" | "privacy" | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNote(signup ? "Account creation isn't connected yet. Your details were not sent or saved." : "Sign-in isn't connected yet. Your details were not sent or saved.");
  }

  return (
    <main className="auth-page font-sans text-foreground">
      <div className="auth-content animate-rise">
        <header className="text-center">
          <img src={train} alt="Vintage train crossing a viaduct, ink illustration" width={1024} height={640} className="auth-train" />
          <h1 className="font-display text-6xl font-light">kup<span className="text-primary">é</span></h1>
          <p className="mt-2 text-xs font-light text-muted-foreground">journeys, beautifully kept</p>
        </header>

        <section className="mt-7 w-full" aria-label={signup ? "Create your account" : "Sign in"}>
          {signup && <h2 id="auth-title" className="text-center font-display text-2xl">Create your account</h2>}
          <form onSubmit={submit} className="mt-5 space-y-4">
            {signup && <div><label htmlFor="name" className="auth-label">Name</label><div className="auth-field"><UserRound aria-hidden="true"/><input id="name" name="name" autoComplete="name" placeholder="Your name" required /></div></div>}
            <div><label htmlFor="email" className="auth-label">Email</label><div className="auth-field"><Mail aria-hidden="true"/><input id="email" name="email" type="email" autoComplete="email" autoCapitalize="none" placeholder="you@email.com" required /></div></div>
            <div><label htmlFor="password" className="auth-label">Password</label><div className="auth-field"><LockKeyhole aria-hidden="true"/><input id="password" name="password" type={visible ? "text" : "password"} autoComplete={signup ? "new-password" : "current-password"} placeholder="Your password" required /><Button type="button" variant="ghost" size="icon" className="shrink-0 text-muted-foreground" title={visible ? "Hide password" : "Show password"} aria-label={visible ? "Hide password" : "Show password"} aria-pressed={visible} onClick={() => setVisible(!visible)}>{visible ? <EyeOff/> : <Eye/>}</Button></div></div>
            <Button type="submit" disabled={!agreed} className="h-12 w-full text-sm">{signup ? "Create account" : "Sign in"}<ArrowRight aria-hidden="true" className="ml-2"/></Button>
          </form>
          <p className="mt-4 flex flex-wrap items-center justify-center gap-x-1 text-sm text-muted-foreground">{signup ? "Already have an account?" : "Don't have an account yet?"}<Button variant="link" asChild className="h-auto px-1 py-1"><Link to={signup ? "/" : "/signup"}>{signup ? "Sign in" : "Create an account"}</Link></Button></p>
          <div className="my-4 flex items-center gap-4" aria-hidden="true"><div className="h-px flex-1 bg-border"/><span className="text-xs text-muted-foreground">or</span><div className="h-px flex-1 bg-border"/></div>
          <Button variant="outline" disabled={!agreed} className="h-12 w-full bg-card" onClick={() => setNote("Google sign-in isn't connected yet.")}><GoogleMark/>Continue with Google</Button>
          {note && <p role="status" className="mt-4 text-center text-xs leading-relaxed text-primary">{note}</p>}
        </section>

        <footer className="mt-7 w-full border-t border-border pt-5">
          <div className="flex items-start gap-3 text-xs leading-5 text-muted-foreground">
            <input id="agreement" type="checkbox" checked={agreed} onChange={(event) => setAgreed(event.target.checked)} className="mt-1 size-4 shrink-0 cursor-pointer accent-primary" />
            <div><label htmlFor="agreement" className="cursor-pointer">I agree to the </label><Button type="button" variant="link" onClick={() => setLegal("terms")} className="h-auto whitespace-normal p-0 text-xs">Terms of Service</Button><span> and </span><Button type="button" variant="link" onClick={() => setLegal("privacy")} className="h-auto whitespace-normal p-0 text-xs">Privacy Policy</Button><span>.</span></div>
          </div>
        </footer>
      </div>
      <Dialog open={legal !== null} onOpenChange={(open) => { if (!open) setLegal(null); }}><DialogContent><DialogHeader><DialogTitle>{legal === "terms" ? "Terms of Service" : "Privacy Policy"}</DialogTitle><DialogDescription>This document isn't available yet. The final terms will be published before account registration opens.</DialogDescription></DialogHeader></DialogContent></Dialog>
    </main>
  );
}
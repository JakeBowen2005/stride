import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string; error?: string }> }) {
  const { next = "/", error } = await searchParams;
  const accounts = process.env.STRIDE_ACCOUNTS_ENABLED === "true";
  return (
    <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10 sm:py-16">
      <Card className="py-6">
        <CardContent className="space-y-5 px-6">
          <div>
            <h1 className="display">Welcome back</h1>
            <p className="mt-2 text-sm text-muted-foreground">{accounts ? "Sign in to your athlete account." : "Enter your Stride password. Sessions last seven days on this device."}</p>
          </div>
          <form action="/auth" method="post" className="space-y-3">
            <input type="hidden" name="next" value={next} />
            {accounts && <div className="space-y-1.5"><Label htmlFor="email">Email</Label><Input id="email" name="email" type="email" autoComplete="email" required /></div>}
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input id="password" name="password" type="password" autoComplete="current-password" required autoFocus />
            </div>
            {error && <p className="text-sm text-destructive">That password didn&apos;t match.</p>}
            <Button type="submit" size="lg" className="w-full">
              Sign in
            </Button>
          </form>
          {accounts && <p className="text-sm"><a className="underline" href="/auth/register">Create an invited account</a> · <a className="underline" href="/auth/reset">Recover account</a></p>}
          {!accounts && !process.env.RENDER && <p className="text-xs text-muted-foreground">The app owner can find the local password in frontend/.env.local.</p>}
        </CardContent>
      </Card>
    </div>
  );
}

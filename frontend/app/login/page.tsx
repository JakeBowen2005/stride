import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string; error?: string }> }) {
  const { next = "/", error } = await searchParams;
  return (
    <div className="mx-auto w-full max-w-sm py-16">
      <Card>
        <CardContent className="space-y-4 pt-6">
          <div>
            <h1 className="text-xl font-semibold">Stride</h1>
            <p className="text-sm text-muted-foreground">Enter your Stride password. Sessions last seven days on this device.</p>
          </div>
          <form action="/auth" method="post" className="space-y-3">
            <input type="hidden" name="next" value={next} />
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input id="password" name="password" type="password" autoComplete="current-password" required autoFocus />
            </div>
            {error && <p className="text-sm text-destructive">That password didn&apos;t match.</p>}
            <Button type="submit" className="w-full">
              Sign in
            </Button>
          </form>
          {!process.env.RENDER && <p className="text-xs text-muted-foreground">The app owner can find the local password in frontend/.env.local.</p>}
        </CardContent>
      </Card>
    </div>
  );
}

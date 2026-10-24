"use client";
import { useState } from "react";
export default function RegisterPage(){
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  return <section className="mx-auto max-w-md space-y-4 py-8"><h1 className="text-xl font-bold">Create your athlete account</h1>
    <p>Use the invitation from the app owner. Your training history and plan stay private to your account.</p>
    <form className="space-y-3" onSubmit={async e=>{e.preventDefault();setBusy(true);setError(""); const f=new FormData(e.currentTarget);
      try {const r=await fetch("/auth/register/submit",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:f.get("name"),email:f.get("email"),password:f.get("password"),invite_code:f.get("invite"),timezone:f.get("timezone"),ai_consent:f.get("ai")==="on"})});const d=await r.json();if(!r.ok)throw new Error(typeof d.detail==="string"?d.detail:"Check the form.");window.location.href="/onboarding";}catch(e){setError(e instanceof Error?e.message:"Could not create account.");}finally{setBusy(false);}}}>
      {[['name','Name','text'],['email','Email','email'],['password','Password (12 or more characters)','password'],['invite','Invitation code','password']].map(([name,label,type])=><label className="block" key={name}>{label}<input className="block min-h-11 w-full rounded border p-2" name={name} type={type} required minLength={name==='password'?12:1} autoComplete={name==='password'?'new-password':name==='invite'?'off':name}/></label>)}
      <label className="block">Timezone<input className="block min-h-11 w-full rounded border p-2" name="timezone" defaultValue={Intl.DateTimeFormat().resolvedOptions().timeZone} required /></label>
      <label className="flex gap-2"><input name="ai" type="checkbox"/>Allow AI coaching to send selected training history, wellness, and my feedback to the configured AI provider. Optional; rule-based plans work without it.</label>
      {error&&<p role="alert">{error}</p>}<button className="min-h-11 rounded border px-4" disabled={busy}>{busy?'Creating…':'Create account'}</button>
    </form><a className="underline" href="/login">Back to sign in</a></section>;
}

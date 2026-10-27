"use client";
import {useEffect,useState} from 'react';
import {apiUrl,getJson,USER_ID} from '@/lib/api';

type Profile={timezone:string|null;ai_consent:boolean};
type Usage={used_percent:number;owner:boolean;spent_usd?:number;cap_usd?:number;month_start:string};

/** Privacy choices in every mode (AI consent is required even for the owner); export and delete need an account. */
export function AccountSettings(){
  const [profile,setProfile]=useState<Profile|null>(null);
  const [usage,setUsage]=useState<Usage|null>(null);
  const [hasAccount,setHasAccount]=useState(false);
  const [message,setMessage]=useState('');
  useEffect(()=>{
    getJson<Profile>(`/users/${USER_ID}`).then(setProfile).catch(()=>setMessage('Account settings could not load.'));
    getJson<{usage?:Usage}>(`/coaching/${USER_ID}/status`).then(s=>setUsage(s?.usage??null)).catch(()=>{});
    fetch('/api/auth/me').then(r=>setHasAccount(r.ok)).catch(()=>{});
  },[]);
  if(!profile)return message?<p role="status">{message}</p>:null;
  return <section className="glass space-y-3 p-4 sm:p-5" aria-label="Account and privacy"><h2 className="text-[13px] font-bold">Account and privacy</h2>
    <form className="space-y-3" onSubmit={async e=>{e.preventDefault();const f=new FormData(e.currentTarget);const r=await fetch(apiUrl(`/users/${USER_ID}/profile`),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({timezone:f.get('timezone'),ai_consent:f.get('ai')==='on'})});if(r.ok)window.dispatchEvent(new Event('stride:preferences-changed'));setMessage(r.ok?'Preferences saved.': 'Could not save preferences.');}}>
      <label className="block">Timezone<input name="timezone" defaultValue={profile.timezone??Intl.DateTimeFormat().resolvedOptions().timeZone} className="block min-h-11 rounded-xl border border-input bg-[var(--glass-inner)] p-2" required/></label>
      <label className="flex gap-2"><input name="ai" type="checkbox" defaultChecked={profile.ai_consent}/>Allow selected training history, wellness, and feedback to be sent to the AI provider for coaching. Rule-based plans work without AI.</label>
      {usage&&<p className="text-xs text-muted-foreground">AI coaching this month: {usage.used_percent}% of your allowance used{usage.owner&&usage.spent_usd!=null&&usage.cap_usd!=null?` ($${usage.spent_usd.toFixed(2)} of $${usage.cap_usd.toFixed(2)})`:''}. When it runs out, saved reviews and the training rules keep working.</p>}
      <button className="min-h-11 rounded-full border border-[var(--glass-border)] bg-[var(--glass-inner)] px-4 text-sm font-semibold transition-colors hover:bg-[var(--row-hover)]">Save privacy preferences</button>
    </form>
    {hasAccount&&<><a className="inline-block min-h-11 underline" href="/api/auth/export">Download my training data</a>
    <details><summary>Delete my account</summary><p>This removes your live training data and provider credentials. Backups expire according to the operator&apos;s retention policy.</p><form className="space-y-2" onSubmit={async e=>{e.preventDefault();const f=new FormData(e.currentTarget);const r=await fetch('/api/auth/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:f.get('password'),confirmation:f.get('confirmation')})});if(r.ok)window.location.href='/login';else setMessage('Deletion failed. Confirm your password and type DELETE.');}}><label className="block">Current password<input className="block min-h-11 rounded-xl border border-input bg-[var(--glass-inner)] p-2" name="password" type="password" required autoComplete="current-password"/></label><label className="block">Type DELETE<input className="block min-h-11 rounded-xl border border-input bg-[var(--glass-inner)] p-2" name="confirmation" required pattern="DELETE"/></label><button className="min-h-11 rounded-full border border-[var(--glass-border)] bg-[var(--glass-inner)] px-4 text-sm font-semibold transition-colors hover:bg-[var(--row-hover)]">Permanently delete my account</button></form></details></>}
    {message&&<p role="status">{message}</p>}
  </section>;
}

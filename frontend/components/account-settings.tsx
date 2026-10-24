"use client";
import {useEffect,useState} from 'react';
import {apiUrl,USER_ID} from '@/lib/api';
export function AccountSettings(){
  const [account,setAccount]=useState<{timezone:string;ai_consent:boolean}|null>(null);
  const [message,setMessage]=useState('');
  useEffect(()=>{fetch('/api/auth/me').then(r=>r.ok?r.json():null).then(setAccount).catch(()=>setMessage('Account settings could not load.'));},[]);
  if(!account)return null;
  return <section className="space-y-3 rounded border p-4" aria-label="Account and privacy"><h2 className="font-medium">Account and privacy</h2>
    <form className="space-y-3" onSubmit={async e=>{e.preventDefault();const f=new FormData(e.currentTarget);const r=await fetch(apiUrl(`/users/${USER_ID}/profile`),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({timezone:f.get('timezone'),ai_consent:f.get('ai')==='on'})});if(r.ok)window.dispatchEvent(new Event('stride:preferences-changed'));setMessage(r.ok?'Preferences saved.': 'Could not save preferences.');}}>
      <label className="block">Timezone<input name="timezone" defaultValue={account.timezone} className="block min-h-11 rounded border p-2" required/></label>
      <label className="flex gap-2"><input name="ai" type="checkbox" defaultChecked={account.ai_consent}/>Allow selected training history, wellness, and feedback to be sent to the AI provider for coaching. Rule-based plans work without AI.</label>
      <button className="min-h-11 rounded border px-3">Save privacy preferences</button>
    </form><a className="inline-block min-h-11 underline" href="/api/auth/export">Download my training data</a>
    <details><summary>Delete my account</summary><p>This removes your live training data and provider credentials. Backups expire according to the operator&apos;s retention policy.</p><form className="space-y-2" onSubmit={async e=>{e.preventDefault();const f=new FormData(e.currentTarget);const r=await fetch('/api/auth/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:f.get('password'),confirmation:f.get('confirmation')})});if(r.ok)window.location.href='/login';else setMessage('Deletion failed. Confirm your password and type DELETE.');}}><label className="block">Current password<input className="block min-h-11 rounded border p-2" name="password" type="password" required autoComplete="current-password"/></label><label className="block">Type DELETE<input className="block min-h-11 rounded border p-2" name="confirmation" required pattern="DELETE"/></label><button className="min-h-11 rounded border px-3">Permanently delete my account</button></form></details>
    {message&&<p role="status">{message}</p>}
  </section>;
}

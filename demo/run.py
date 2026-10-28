#!/usr/bin/env python3
"""Launch a branch's synthetic athlete separately on localhost:3100/8100 (or --port N / N+5000). --ai uses backend/.env's OpenAI key."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import shutil
import tempfile
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
SCENARIOS=sorted(p.stem for p in (ROOT/'demo/scenarios').glob('*.json'))

def main():
    default=json.loads((ROOT/'demo/default-scenario.json').read_text())['scenario']
    parser=argparse.ArgumentParser()
    parser.add_argument('scenario',nargs='?',default=default,choices=SCENARIOS)
    parser.add_argument('--port',type=int,default=3100,help='frontend port; the API uses port+5000 (run two demos side by side)')
    parser.add_argument('--ai',action='store_true',help="real OpenAI calls (plan-change requests, reviews) with backend/.env's key; costs count against the demo DB's own budget")
    args=parser.parse_args()
    web,api=args.port,args.port+5000
    for port in (web,api):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            try:sock.bind(('127.0.0.1',port))
            except OSError:raise SystemExit(f'Port {port} is in use. Stop the other demo first; your real app is unaffected.')
    python=ROOT/'backend/venv/bin/python'
    if not python.exists():raise SystemExit('First set up backend/venv and install backend requirements.')
    if not (ROOT/'frontend/node_modules').is_dir():raise SystemExit('First install frontend dependencies with npm ci in frontend/.')
    folder=ROOT/'.demo'/args.scenario;folder.mkdir(parents=True,exist_ok=True)
    target=folder/'stride.db'
    if not target.exists():subprocess.run([str(python),str(ROOT/'demo/seed.py'),'--scenario',args.scenario,'--database',str(target)],check=True)
    env=dict(os.environ,DATABASE_URL=f'sqlite:///{target}',GARMIN_POLL_MINUTES='0',GARMIN_API_KEY='',OPENAI_API_KEY='',ANTHROPIC_API_KEY='',OPENAI_AUTO_REVIEWS='false',ATHLETE_PROFILE_DOC='',
             BACKEND_URL=f'http://127.0.0.1:{api}',STRIDE_DEMO_SCENARIO=args.scenario,STRIDE_DEMO_AI='1' if args.ai else '',STRIDE_PASSWORD='')
    if args.ai:
        # Drop the blank override so the backend reads OPENAI_API_KEY from backend/.env; the synthetic athlete consents.
        env.pop('OPENAI_API_KEY')
        with sqlite3.connect(target) as db:db.execute('UPDATE users SET ai_consent=1 WHERE id=1')
    frontend=Path(tempfile.mkdtemp(prefix='frontend-',dir=folder))
    shutil.copytree(ROOT/'frontend',frontend,dirs_exist_ok=True,ignore=shutil.ignore_patterns('node_modules','.next*','.env*','*.tsbuildinfo'))
    (frontend/'node_modules').symlink_to(ROOT/'frontend/node_modules',target_is_directory=True)
    processes=[]
    try:
        processes.append(subprocess.Popen([str(python),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(api)],cwd=ROOT/'backend',env=env,start_new_session=True))
        processes.append(subprocess.Popen(['npx','next','dev','--webpack','-H','127.0.0.1','-p',str(web)],cwd=frontend,env=env,start_new_session=True))
        print(f'\nSynthetic {args.scenario}: http://localhost:{web} · DB {target}\nGarmin disabled; AI calls {"ON (real OpenAI, costs money)" if args.ai else "disabled"}. Ctrl+C stops ONLY this demo.\n',flush=True)
        while all(p.poll() is None for p in processes):time.sleep(1)
    except KeyboardInterrupt:pass
    finally:
        for p in processes:
            try:os.killpg(p.pid,signal.SIGTERM)
            except ProcessLookupError:pass
        for p in processes:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                p.wait()

if __name__=='__main__':main()

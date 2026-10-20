#!/usr/bin/env python3
"""Launch a branch's synthetic athlete separately on localhost:3100/8100."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import shutil
import tempfile
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]

def main():
    default=json.loads((ROOT/'demo/default-scenario.json').read_text())['scenario']
    parser=argparse.ArgumentParser()
    parser.add_argument('scenario',nargs='?',default=default,choices=['sub3-marathon','sub17-5k','trail-100k'])
    args=parser.parse_args()
    for port in (3100,8100):
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
    env=dict(os.environ,DATABASE_URL=f'sqlite:///{target}',GARMIN_POLL_MINUTES='0',GARMIN_TOKENSTORE=str(folder/'no-garmin-tokens'),OPENAI_API_KEY='',ANTHROPIC_API_KEY='',OPENAI_AUTO_REVIEWS='false',ATHLETE_PROFILE_DOC='',
             BACKEND_URL='http://127.0.0.1:8100',STRIDE_DEMO_SCENARIO=args.scenario,STRIDE_PASSWORD='')
    frontend=Path(tempfile.mkdtemp(prefix='frontend-',dir=folder))
    shutil.copytree(ROOT/'frontend',frontend,dirs_exist_ok=True,ignore=shutil.ignore_patterns('node_modules','.next*','.env*','*.tsbuildinfo'))
    (frontend/'node_modules').symlink_to(ROOT/'frontend/node_modules',target_is_directory=True)
    processes=[]
    try:
        processes.append(subprocess.Popen([str(python),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8100'],cwd=ROOT/'backend',env=env,start_new_session=True))
        processes.append(subprocess.Popen(['npx','next','dev','--webpack','-H','127.0.0.1','-p','3100'],cwd=frontend,env=env,start_new_session=True))
        print(f'\nSynthetic {args.scenario}: http://localhost:3100 · DB {target}\nGarmin and AI calls disabled. Ctrl+C stops ONLY this demo.\n',flush=True)
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

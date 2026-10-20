#!/usr/bin/env python3
"""Create a NEW isolated synthetic DB. Never opens or overwrites the personal DB."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SCENARIOS=sorted(p.stem for p in (ROOT/'demo/scenarios').glob('*.json'))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--scenario',choices=SCENARIOS,required=True)
    parser.add_argument('--database',type=Path,required=True)
    args=parser.parse_args();target=args.database.resolve()
    if target==(ROOT/'backend/stride.db').resolve() or target.exists():
        raise SystemExit('Refusing to use the personal database or overwrite an existing file.')
    target.parent.mkdir(parents=True,exist_ok=True)
    fd, temporary=tempfile.mkstemp(prefix='stride-initializing-',suffix='.db',dir=target.parent)
    os.close(fd)
    staging=Path(temporary)
    os.environ.update(DATABASE_URL=f'sqlite:///{staging}',GARMIN_POLL_MINUTES='0',GARMIN_TOKENSTORE=str(target.parent/'no-garmin-tokens'),
                      OPENAI_API_KEY='',ANTHROPIC_API_KEY='',OPENAI_AUTO_REVIEWS='false',ATHLETE_PROFILE_DOC='')
    sys.path.insert(0,str(ROOT/'backend'))
    from app.main import app  # noqa: F401 — create schema only in the NEW target
    from app.database import SessionLocal, engine
    from app.services.demo_seed import seed_demo
    profile=json.loads((ROOT/'demo/scenarios'/f'{args.scenario}.json').read_text())
    try:
        with SessionLocal() as db:result=seed_demo(db,profile)
        with engine.connect() as connection:connection.exec_driver_sql('PRAGMA wal_checkpoint(TRUNCATE)')
        engine.dispose()
        os.link(staging,target)  # atomic publication, refusing to overwrite a concurrent file
    finally:
        engine.dispose()
        for suffix in ('','-wal','-shm'):
            file=Path(str(staging)+suffix)
            if file.exists():file.unlink()
    (target.parent/'scenario.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__':main()

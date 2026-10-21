"""Print exactly what the AI coach is sent, with a size breakdown per section.

Works on a temporary COPY of the database, so it never writes to the source file.
No provider call is made.

    venv/bin/python scripts/dump_coach_context.py --db path/to/copy.db --plan 12
    venv/bin/python scripts/dump_coach_context.py --db path/to/copy.db --activity 345 --full
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--db', required=True, help='SQLite file to read (copied first)')
    parser.add_argument('--user', type=int, default=1)
    parser.add_argument('--activity', type=int, help='review a run (scope "run")')
    parser.add_argument('--plan', type=int, help='review a plan (scope "week"); default is the active plan')
    parser.add_argument('--full', action='store_true', help='also print the full JSON payload')
    args = parser.parse_args()

    source = Path(args.db).resolve()
    if not source.exists():
        sys.exit(f'No database at {source}')
    workdir = Path(tempfile.mkdtemp(prefix='stride-context-'))
    copy = workdir / 'context.db'
    shutil.copy2(source, copy)
    os.environ['DATABASE_URL'] = f'sqlite:///{copy}'
    os.environ['GARMIN_POLL_MINUTES'] = '0'
    os.environ['OPENAI_AUTO_REVIEWS'] = 'false'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    import app.models  # noqa: F401 — registers every table
    from app.database import Base, SessionLocal, add_missing_columns, engine
    from app.services.coaching import build_context
    from app.services.openai_coach import INSTRUCTIONS, model_payload

    Base.metadata.create_all(bind=engine)  # bring an older copy up to the current schema
    add_missing_columns()
    with SessionLocal() as db:
        context, research, fingerprint, _ = build_context(args.user, db, args.activity, args.plan)
    payload = model_payload(context, research)
    context = payload['context']

    size = lambda value: len(json.dumps(value, ensure_ascii=False, default=str))
    total = size(payload)
    print(f"scope={context['review_scope']}  fingerprint={fingerprint[:12]}  "
          f"instructions={len(INSTRUCTIONS):,} chars  payload={total:,} chars (~{total // 4:,} tokens)\n")
    print('context section           chars')
    for key, value in sorted(context.items(), key=lambda kv: -size(kv[1])):
        print(f'  {key:<22}{size(value):>8,}')
    print('research source           chars')
    for source_doc in research:
        print(f"  {source_doc['id']:<22}{len(source_doc['excerpt']):>8,}")
    if args.full:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    shutil.rmtree(workdir, ignore_errors=True)


if __name__ == '__main__':
    main()

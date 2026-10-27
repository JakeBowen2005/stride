"""Copy a migrated read-only SQLite snapshot into an EMPTY PostgreSQL database.

Never points at the live writer. Run app.schema on a disposable snapshot first,
freeze writes during cutover, retain backups, and validate counts before switching.
"""
import argparse
from pathlib import Path
from sqlalchemy import create_engine, select, func, Integer, text
from app.database import Base
import app.models  # noqa: F401
from app.schema import upgrade


def transfer(source,destination):
    source=Path(source).resolve()
    if not source.is_file():raise ValueError('Source snapshot does not exist')
    src=create_engine(f'sqlite:///file:{source}?mode=ro&uri=true')
    dst=create_engine(destination,pool_pre_ping=True)
    if dst.dialect.name!='postgresql':raise ValueError('Destination must be PostgreSQL')
    upgrade(dst)
    counts={}
    with src.connect() as reader,dst.begin() as writer:
        for table in Base.metadata.sorted_tables:
            if writer.execute(select(func.count()).select_from(table)).scalar():
                raise ValueError('Destination must contain no athlete data')
        for table in Base.metadata.sorted_tables:
            count=0
            result=reader.execute(select(table)).mappings()
            while batch:=result.fetchmany(200):
                writer.execute(table.insert(),[dict(row) for row in batch]);count+=len(batch)
            if writer.execute(select(func.count()).select_from(table)).scalar()!=count:
                raise ValueError('Transfer count mismatch')
            counts[table.name]=count
            if len(table.primary_key.columns)==1:
                column=next(iter(table.primary_key.columns))
                if isinstance(column.type,Integer):
                    sequence=writer.execute(text('SELECT pg_get_serial_sequence(:table,:column)'),{'table':table.name,'column':column.name}).scalar()
                    if sequence:
                        value=writer.execute(select(func.max(column))).scalar() or 0
                        writer.execute(text('SELECT setval(:sequence,:value,false)'),{'sequence':sequence,'value':value+1})
    return counts


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-snapshot',required=True,type=Path)
    parser.add_argument('--destination-url',required=True)
    args=parser.parse_args()
    print(transfer(args.source_snapshot,args.destination_url))

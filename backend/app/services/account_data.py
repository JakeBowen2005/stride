"""Ownership filters shared by export and erasure, including indirect children."""
from sqlalchemy import select, or_
from app.database import Base


def owned_tables(user_id):
    filters = {}
    for table in Base.metadata.sorted_tables:
        if table.name == 'users':
            filters[table.name] = table.c.id == user_id
        elif 'user_id' in table.c:
            filters[table.name] = table.c.user_id == user_id
        else:
            parents=[]
            for fk in table.foreign_keys:
                parent=fk.column.table
                if parent.name in filters:
                    parents.append(fk.parent.in_(select(fk.column).where(filters[parent.name])))
            if parents:
                filters[table.name]=or_(*parents)
    return [(t,filters[t.name]) for t in Base.metadata.sorted_tables if t.name in filters]

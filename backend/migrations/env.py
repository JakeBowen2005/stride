from alembic import context
from app.database import engine
connection=context.config.attributes.get('connection')
if connection is not None:
    context.configure(connection=connection)
    with context.begin_transaction():context.run_migrations()
else:
    with engine.begin() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():context.run_migrations()

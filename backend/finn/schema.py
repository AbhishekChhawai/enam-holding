"""Print the DDL for the actual SQLAlchemy models:  python -m finn.schema > financial_schema.sql"""
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateIndex, CreateTable

from .db import Base


def ddl(dialect_name: str = "sqlite") -> str:
    dialect = postgresql.dialect() if dialect_name == "postgresql" else sqlite.dialect()
    out = [f"-- FINN schema, generated from finn/db.py for {dialect_name}. Do not edit by hand.\n"]
    for t in Base.metadata.sorted_tables:
        out.append(str(CreateTable(t).compile(dialect=dialect)).strip() + ";\n")
        for ix in t.indexes:
            out.append(str(CreateIndex(ix).compile(dialect=dialect)).strip() + ";\n")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    print(ddl(sys.argv[1] if len(sys.argv) > 1 else "sqlite"))

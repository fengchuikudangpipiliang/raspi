import sqlite3
from pathlib import Path

from scripts.config.config import cfg


def build_table_text(table_name, columns, rows):
    headers = [column[1] for column in columns]
    display_rows = [headers]

    for row in rows:
        display_rows.append(["" if value is None else str(value) for value in row])

    widths = []
    for col_index in range(len(headers)):
        widths.append(max(len(row[col_index]) for row in display_rows))

    def make_border():
        return "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def make_row(values):
        cells = []
        for value, width in zip(values, widths):
            cells.append(f" {value.ljust(width)} ")
        return "|" + "|".join(cells) + "|"

    lines = [f"Table: {table_name}", make_border(), make_row(headers), make_border()]

    if rows:
        for row in rows:
            values = ["" if value is None else str(value) for value in row]
            lines.append(make_row(values))
    else:
        empty_values = ["(empty)"] + [""] * (len(headers) - 1)
        lines.append(make_row(empty_values))

    lines.append(make_border())
    return "\n".join(lines) + "\n"


def main():
    db_path = Path(cfg.sqlite_path).resolve()
    output_dir = db_path.parent / "db_tables"

    if not db_path.exists():
        print("Database file does not exist yet.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]

    if not tables:
        connection.close()
        print("No tables found.")
        return

    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        columns = cursor.fetchall()
        cursor.execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()

        table_text = build_table_text(table, columns, rows)
        output_path = output_dir / f"{table}.txt"
        output_path.write_text(table_text, encoding="utf-8")

    connection.close()
    print(f"Exported {len(tables)} table file(s) to: {output_dir}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Import seed data from seed_data_expansion.sql into Docker MySQL.
- Reads each SQL statement
- For INSERT statements: validates columns against DESCRIBE, fixes mismatches
- For UPDATE statements: validates columns exist
- Uses INSERT IGNORE to skip duplicates
- Saves fixed SQL to seed_data_expansion_fixed.sql
"""

import pymysql
import re
import sys
import os

DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3307,
    'user': 'root',
    'password': 'chatbi2024',
    'database': 'qft_datamart',
    'charset': 'utf8mb4',
}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_FILE = os.path.join(BASE_DIR, 'data', 'seed_data_expansion.sql')
FIXED_FILE = os.path.join(BASE_DIR, 'data', 'seed_data_expansion_fixed.sql')


def get_table_columns(cursor, table_name):
    """Get column info for a table."""
    cursor.execute(f"DESCRIBE `{table_name}`")
    rows = cursor.fetchall()
    cols = {}
    for r in rows:
        cols[r[0]] = {
            'type': r[1],
            'nullable': r[2] == 'YES',
            'key': r[3],
            'default': r[4],
            'extra': r[5],
        }
    return cols


def default_value_for_type(col_type):
    """Generate a safe default value for a given MySQL column type."""
    t = col_type.lower()
    if 'bigint' in t or 'int' in t:
        return '0'
    elif 'decimal' in t or 'float' in t or 'double' in t:
        return '0.00'
    elif 'datetime' in t or 'timestamp' in t:
        return "'2024-01-01 00:00:00'"
    elif 'date' in t:
        return "'2024-01-01'"
    elif 'tinyint' in t:
        return '0'
    elif 'varchar' in t or 'text' in t or 'char' in t:
        return "''"
    else:
        return "''"


def split_values(values_str):
    """Split comma-separated values, respecting quoted strings."""
    values = []
    current = []
    in_str = False
    esc = False
    qchar = None

    for ch in values_str:
        if esc:
            current.append(ch)
            esc = False
            continue
        if ch == '\\':
            current.append(ch)
            esc = True
            continue
        if in_str:
            current.append(ch)
            if ch == qchar:
                in_str = False
            continue
        if ch in ("'", '"'):
            in_str = True
            qchar = ch
            current.append(ch)
            continue
        if ch == ',':
            values.append(''.join(current).strip())
            current = []
            continue
        current.append(ch)

    last = ''.join(current).strip()
    if last:
        values.append(last)
    return values


def parse_sql_file(filepath):
    """Parse SQL file into individual statements, stripping comments."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Remove comment-only lines
    lines = content.split('\n')
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('--'):
            clean_lines.append('')
        else:
            clean_lines.append(line)
    content = '\n'.join(clean_lines)

    # Split by semicolons, respecting strings
    statements = []
    current = []
    in_string = False
    escape_next = False
    quote_char = None

    for ch in content:
        if escape_next:
            current.append(ch)
            escape_next = False
            continue
        if ch == '\\':
            current.append(ch)
            escape_next = True
            continue
        if in_string:
            current.append(ch)
            if ch == quote_char:
                in_string = False
            continue
        if ch in ("'", '"'):
            in_string = True
            quote_char = ch
            current.append(ch)
            continue
        if ch == ';':
            stmt = ''.join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            continue
        current.append(ch)

    stmt = ''.join(current).strip()
    if stmt:
        statements.append(stmt)
    return statements


def parse_insert(stmt):
    """Parse INSERT statement: returns (table, columns, value_tuples) or None."""
    pattern = r'INSERT\s+(?:IGNORE\s+)?INTO\s+`?(\w+)`?\s*\(([^)]+)\)\s*VALUES\s*(.*)'
    m = re.match(pattern, stmt, re.DOTALL | re.IGNORECASE)
    if not m:
        return None

    table_name = m.group(1)
    columns = [c.strip().strip('`') for c in m.group(2).split(',')]
    values_str = m.group(3).strip()

    # Parse value tuples
    tuples = []
    current_tuple = []
    depth = 0
    in_str = False
    esc = False
    qchar = None

    for ch in values_str:
        if esc:
            current_tuple.append(ch)
            esc = False
            continue
        if ch == '\\':
            current_tuple.append(ch)
            esc = True
            continue
        if in_str:
            current_tuple.append(ch)
            if ch == qchar:
                in_str = False
            continue
        if ch in ("'", '"'):
            in_str = True
            qchar = ch
            current_tuple.append(ch)
            continue
        if ch == '(':
            depth += 1
            if depth == 1:
                current_tuple = []
                continue
            current_tuple.append(ch)
            continue
        if ch == ')':
            depth -= 1
            if depth == 0:
                tuples.append(''.join(current_tuple))
                continue
            current_tuple.append(ch)
            continue
        if depth > 0:
            current_tuple.append(ch)

    return table_name, columns, tuples


def parse_update(stmt):
    """Parse UPDATE statement: returns (table, set_clause, where_clause) or None."""
    pattern = r'UPDATE\s+`?(\w+)`?\s+SET\s+(.*?)\s+WHERE\s+(.*)'
    m = re.match(pattern, stmt, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)


def get_missing_not_null_cols(table_cols, provided_cols):
    """Get NOT NULL columns without defaults that are missing from the provided list."""
    missing = {}
    for name, info in table_cols.items():
        if name in provided_cols:
            continue
        if 'auto_increment' in info['extra']:
            continue
        if info['default'] is not None:
            continue
        if 'CURRENT_TIMESTAMP' in (info.get('extra') or ''):
            continue
        # Check if it's timestamp with default
        if info['type'] == 'timestamp' and 'DEFAULT_GENERATED' in (info.get('extra') or ''):
            continue
        if not info['nullable']:
            missing[name] = info
    return missing


def main():
    print("=" * 70)
    print("Seed Data Import - Column Validation & Fix")
    print("=" * 70)

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # Cache table structures
    cursor.execute("SHOW TABLES")
    all_tables = {r[0] for r in cursor.fetchall()}
    table_cache = {}

    def get_cols(tname):
        if tname not in table_cache:
            table_cache[tname] = get_table_columns(cursor, tname) if tname in all_tables else None
        return table_cache[tname]

    # Parse SQL file
    print(f"\nReading: {SQL_FILE}")
    statements = parse_sql_file(SQL_FILE)
    print(f"Found {len(statements)} SQL statements\n")

    fixed_stmts = []
    stats = {
        'update_ok': 0, 'update_fail': 0,
        'insert_ok': 0, 'insert_fail': 0,
        'rows_inserted': 0, 'rows_skipped': 0, 'rows_error': 0,
    }

    for idx, stmt in enumerate(statements):
        stmt_type = stmt.strip().split()[0].upper()

        # ===================== UPDATE =====================
        if stmt_type == 'UPDATE':
            parsed = parse_update(stmt)
            if not parsed:
                continue
            table_name, set_clause, where_clause = parsed
            if table_name not in all_tables:
                print(f"[SKIP] Table {table_name} not found")
                continue

            fixed_sql = f"UPDATE `{table_name}` SET {set_clause} WHERE {where_clause}"
            fixed_stmts.append(fixed_sql)

            try:
                cursor.execute(fixed_sql)
                conn.commit()
                stats['update_ok'] += 1
            except Exception as e:
                print(f"[ERROR] UPDATE {table_name}: {e}")
                conn.rollback()
                stats['update_fail'] += 1

        # ===================== INSERT =====================
        elif stmt_type == 'INSERT':
            parsed = parse_insert(stmt)
            if not parsed:
                continue
            table_name, sql_columns, value_tuples = parsed
            table_cols = get_cols(table_name)
            if table_cols is None:
                print(f"[SKIP] Table {table_name} not found")
                continue

            real_col_set = set(table_cols.keys())
            changes = []

            # --- Step 1: Check if column count matches value count ---
            if value_tuples:
                first_vals = split_values(value_tuples[0])
                if len(first_vals) != len(sql_columns):
                    # Column/value count mismatch
                    # The values likely match only the first N columns
                    val_count = len(first_vals)
                    old_cols = sql_columns[:]
                    sql_columns = sql_columns[:val_count]
                    removed = old_cols[val_count:]
                    changes.append(f"  Trimmed columns to match {val_count} values (removed: {removed})")

            # --- Step 2: Verify all columns exist in table ---
            final_cols = []
            remove_indices = []
            for i, col in enumerate(sql_columns):
                if col in real_col_set:
                    final_cols.append(col)
                else:
                    # Try known mappings or case-insensitive match
                    lower_map = {k.lower(): k for k in real_col_set}
                    if col.lower() in lower_map:
                        real_name = lower_map[col.lower()]
                        changes.append(f"  Column case fix: {col} -> {real_name}")
                        final_cols.append(real_name)
                    else:
                        changes.append(f"  Column {col} not in table, removed")
                        remove_indices.append(i)

            # Remove values for removed columns
            if remove_indices:
                new_tuples = []
                for vt in value_tuples:
                    vals = split_values(vt)
                    vals = [v for i, v in enumerate(vals) if i not in remove_indices]
                    new_tuples.append(', '.join(vals))
                value_tuples = new_tuples

            # --- Step 3: Add missing NOT NULL columns ---
            missing = get_missing_not_null_cols(table_cols, set(final_cols))
            for col_name, col_info in missing.items():
                default = default_value_for_type(col_info['type'])
                changes.append(f"  Added NOT NULL column: {col_name} ({col_info['type']}) = {default}")
                final_cols.append(col_name)
                value_tuples = [vt + ', ' + default for vt in value_tuples]

            # --- Step 4: Final validation - pad/trim values per row ---
            col_count = len(final_cols)
            clean_tuples = []
            for i, vt in enumerate(value_tuples):
                vals = split_values(vt)
                if len(vals) < col_count:
                    # Pad with defaults
                    while len(vals) < col_count:
                        ci = len(vals)
                        cname = final_cols[ci]
                        cinfo = table_cols.get(cname, {})
                        if cinfo.get('nullable'):
                            vals.append('NULL')
                        else:
                            vals.append(default_value_for_type(cinfo.get('type', 'varchar(50)')))
                    vt = ', '.join(vals)
                elif len(vals) > col_count:
                    vals = vals[:col_count]
                    vt = ', '.join(vals)
                clean_tuples.append(vt)

            if changes:
                print(f"[FIX] {table_name} ({len(clean_tuples)} rows):")
                for c in changes:
                    print(c)

            # Build fixed SQL for the file
            cols_str = ', '.join(f'`{c}`' for c in final_cols)
            all_values_str = ',\n'.join(f'({vt})' for vt in clean_tuples)
            fixed_stmts.append(f"INSERT IGNORE INTO `{table_name}` ({cols_str}) VALUES\n{all_values_str}")

            # Execute row by row
            ok = 0
            skip = 0
            err = 0
            for i, vt in enumerate(clean_tuples):
                row_sql = f"INSERT IGNORE INTO `{table_name}` ({cols_str}) VALUES ({vt})"
                try:
                    cursor.execute(row_sql)
                    if cursor.rowcount > 0:
                        ok += 1
                    else:
                        skip += 1
                except pymysql.err.IntegrityError as e:
                    skip += 1
                except Exception as e:
                    err += 1
                    if err <= 3:  # Only show first 3 errors per table
                        print(f"  [ERROR] Row {i+1}: {str(e)[:200]}")
                    conn.rollback()

            conn.commit()
            stats['rows_inserted'] += ok
            stats['rows_skipped'] += skip
            stats['rows_error'] += err
            stats['insert_ok'] += 1

            status_parts = []
            if ok > 0:
                status_parts.append(f"{ok} inserted")
            if skip > 0:
                status_parts.append(f"{skip} skipped")
            if err > 0:
                status_parts.append(f"{err} errors")
            print(f"  {table_name}: {', '.join(status_parts)}")

    # Save fixed SQL
    print(f"\n{'=' * 70}")
    print(f"Saving fixed SQL: {FIXED_FILE}")
    with open(FIXED_FILE, 'w', encoding='utf-8') as f:
        f.write("-- ============================================================================\n")
        f.write("-- Fixed seed data (auto-generated by import_seed_data.py)\n")
        f.write("-- Column names corrected to match real table structure\n")
        f.write("-- Uses INSERT IGNORE to skip duplicates\n")
        f.write("-- ============================================================================\n\n")
        for s in fixed_stmts:
            f.write(s + ';\n\n')
    print(f"Saved {len(fixed_stmts)} statements")

    # Verify final row counts
    print(f"\n{'=' * 70}")
    print("Final table row counts:")

    touched_tables = set()
    for s in fixed_stmts:
        m = re.search(r'(?:INSERT|UPDATE)\s+(?:IGNORE\s+)?(?:INTO\s+)?`?(\w+)`?', s, re.IGNORECASE)
        if m:
            touched_tables.add(m.group(1))

    total_rows = 0
    for table in sorted(touched_tables):
        try:
            cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
            count = cursor.fetchone()[0]
            total_rows += count
            print(f"  {table}: {count}")
        except Exception as e:
            print(f"  {table}: ERROR - {e}")

    print(f"\n  TOTAL: {total_rows}")

    print(f"\n{'=' * 70}")
    print("Summary:")
    print(f"  UPDATE: {stats['update_ok']} ok, {stats['update_fail']} failed")
    print(f"  INSERT: {stats['insert_ok']} statements processed")
    print(f"  Rows: {stats['rows_inserted']} inserted, {stats['rows_skipped']} skipped (dup), {stats['rows_error']} errors")
    print(f"{'=' * 70}")

    cursor.close()
    conn.close()


if __name__ == '__main__':
    main()

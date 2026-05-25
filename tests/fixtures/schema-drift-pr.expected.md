## What
Adds [SchemaDriftTest.php](https://github.com/acme/widget/blob/main/test/php/SchemaDriftTest.php) — a PHPUnit test that fails when [setup-database-prod.sql](https://github.com/acme/widget/blob/main/src/api/setup-database-prod.sql) and [schema-sqlite.sql](https://github.com/acme/widget/blob/main/test/php/schema-sqlite.sql) drift apart at the table-and-column-name level.

## Why
The PHPUnit suite runs against an SQLite fixture, while production runs against MySQL. The two schema files have been kept in sync by convention only.

## How the parser handles edge cases
- **`` `key` `` is a real column name on `ballots`**, and `KEY` is also a MySQL table-constraint keyword. The parser treats any backtick-quoted leading token as a column unconditionally [SchemaDriftTest.php:178-186](https://github.com/acme/widget/blob/main/test/php/SchemaDriftTest.php#L178-L186). The fixture's `` `key` `` column is now backticked too [schema-sqlite.sql:6](https://github.com/acme/widget/blob/main/test/php/schema-sqlite.sql#L6).
- **Trailing-clause variation.** The trailing pattern is `[^();]*;` [SchemaDriftTest.php:191-198](https://github.com/acme/widget/blob/main/test/php/SchemaDriftTest.php#L191-L198).

## Drift-guard tests
- `testSqliteFixtureHasNoTablesMissingFromProd` [SchemaDriftTest.php:54-67](https://github.com/acme/widget/blob/main/test/php/SchemaDriftTest.php#L54-L67) — fixture must be a subset of prod.
- `testColumnNamesMatchForSharedTables` [SchemaDriftTest.php:69-103](https://github.com/acme/widget/blob/main/test/php/SchemaDriftTest.php#L69-L103) — exact column-name parity per shared table.

## Parser-sanity tests
- `testParserFindsExactExpectedProdTables` [SchemaDriftTest.php:124-146](https://github.com/acme/widget/blob/main/test/php/SchemaDriftTest.php#L124-L146) locks the prod table list.
- `testKnownConstraintKeywordColumnIsRecognised` [SchemaDriftTest.php:148-160](https://github.com/acme/widget/blob/main/test/php/SchemaDriftTest.php#L148-L160) asserts `key` survives parsing.

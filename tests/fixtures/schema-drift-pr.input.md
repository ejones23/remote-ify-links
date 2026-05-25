## What
Adds `@/tmp/fake-repo-root-for-tests/test/php/SchemaDriftTest.php` — a PHPUnit test that fails when `@/tmp/fake-repo-root-for-tests/src/api/setup-database-prod.sql` and `@/tmp/fake-repo-root-for-tests/test/php/schema-sqlite.sql` drift apart at the table-and-column-name level.

## Why
The PHPUnit suite runs against an SQLite fixture, while production runs against MySQL. The two schema files have been kept in sync by convention only.

## How the parser handles edge cases
- **`` `key` `` is a real column name on `ballots`**, and `KEY` is also a MySQL table-constraint keyword. The parser treats any backtick-quoted leading token as a column unconditionally `@/tmp/fake-repo-root-for-tests/test/php/SchemaDriftTest.php:178-186`. The fixture's `` `key` `` column is now backticked too `@/tmp/fake-repo-root-for-tests/test/php/schema-sqlite.sql:6`.
- **Trailing-clause variation.** The trailing pattern is `[^();]*;` `@/tmp/fake-repo-root-for-tests/test/php/SchemaDriftTest.php:191-198`.

## Drift-guard tests
- `testSqliteFixtureHasNoTablesMissingFromProd` `@/tmp/fake-repo-root-for-tests/test/php/SchemaDriftTest.php:54-67` — fixture must be a subset of prod.
- `testColumnNamesMatchForSharedTables` `@/tmp/fake-repo-root-for-tests/test/php/SchemaDriftTest.php:69-103` — exact column-name parity per shared table.

## Parser-sanity tests
- `testParserFindsExactExpectedProdTables` `@/tmp/fake-repo-root-for-tests/test/php/SchemaDriftTest.php:124-146` locks the prod table list.
- `testKnownConstraintKeywordColumnIsRecognised` `@/tmp/fake-repo-root-for-tests/test/php/SchemaDriftTest.php:148-160` asserts `key` survives parsing.

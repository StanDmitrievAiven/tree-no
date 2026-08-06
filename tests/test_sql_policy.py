import unittest

from sql_policy import SQLPolicyError, validate_read_only_sql


class ReadOnlySqlTests(unittest.TestCase):
    def test_allows_select_and_removes_comments(self):
        self.assertEqual(
            validate_read_only_sql("-- metadata query\nSELECT * FROM system.runtime.nodes;"),
            "SELECT * FROM system.runtime.nodes",
        )

    def test_allows_with_select(self):
        self.assertEqual(
            validate_read_only_sql("WITH t AS (SELECT 1 AS id) SELECT id FROM t"),
            "WITH t AS (SELECT 1 AS id) SELECT id FROM t",
        )

    def test_rejects_write_verb(self):
        with self.assertRaisesRegex(SQLPolicyError, "not permitted"):
            validate_read_only_sql("DELETE FROM postgres.public.events")

    def test_rejects_write_hidden_in_explain(self):
        with self.assertRaisesRegex(SQLPolicyError, "not permitted"):
            validate_read_only_sql("EXPLAIN ANALYZE INSERT INTO x SELECT 1")

    def test_rejects_multiple_statements(self):
        with self.assertRaisesRegex(SQLPolicyError, "exactly one"):
            validate_read_only_sql("SELECT 1; SELECT 2")

    def test_allows_write_words_inside_string_literals(self):
        self.assertEqual(
            validate_read_only_sql("SELECT 'DELETE is text' AS message"),
            "SELECT 'DELETE is text' AS message",
        )


if __name__ == "__main__":
    unittest.main()

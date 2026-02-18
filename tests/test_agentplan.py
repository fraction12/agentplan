#!/usr/bin/env python3
"""Tests for agentplan CLI."""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import agentplan


class Base(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        os.environ["AGENTPLAN_DB"] = self.db_path
        os.environ["AGENTPLAN_DIR"] = self.tmpdir
        conn = agentplan.get_connection(self.db_path)
        agentplan.init_db(conn)
        conn.commit()
        conn.close()

    def tearDown(self):
        for f in os.listdir(self.tmpdir):
            os.unlink(os.path.join(self.tmpdir, f))
        os.rmdir(self.tmpdir)
        os.environ.pop("AGENTPLAN_DB", None)
        os.environ.pop("AGENTPLAN_DIR", None)

    def cli(self, args):
        out, err = StringIO(), StringIO()
        code = 0
        with patch("sys.argv", ["agentplan"] + args), \
             patch("sys.stdout", out), patch("sys.stderr", err):
            try:
                agentplan.main()
            except SystemExit as e:
                code = e.code if e.code is not None else 0
        return out.getvalue(), err.getvalue(), code

    def conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c


# ===== Project CRUD =====

class TestProjectCreate(Base):
    def test_create_simple(self):
        out, _, code = self.cli(["create", "My Project"])
        self.assertEqual(code, 0)
        self.assertIn("my-project", out)

    def test_create_with_tickets(self):
        out, _, code = self.cli(["create", "Build CLI", "--ticket", "Write code", "--ticket", "Test"])
        self.assertEqual(code, 0)
        self.assertIn("2 ticket(s)", out)

    def test_create_with_notes(self):
        self.cli(["create", "Noted", "--notes", "Important stuff"])
        c = self.conn()
        row = c.execute("SELECT notes FROM projects WHERE slug='noted'").fetchone()
        self.assertEqual(row["notes"], "Important stuff")
        c.close()

    def test_create_slug_collision(self):
        self.cli(["create", "Foo"])
        self.cli(["create", "Foo"])
        c = self.conn()
        slugs = [r["slug"] for r in c.execute("SELECT slug FROM projects ORDER BY id").fetchall()]
        self.assertEqual(slugs, ["foo", "foo-2"])
        c.close()

    def test_create_special_chars(self):
        out, _, _ = self.cli(["create", "Hello World! @#$%"])
        self.assertIn("hello-world", out)


class TestProjectList(Base):
    def test_list_empty(self):
        _, _, code = self.cli(["list"])
        self.assertEqual(code, 1)

    def test_list_active(self):
        self.cli(["create", "Alpha"])
        self.cli(["create", "Beta"])
        out, _, code = self.cli(["list"])
        self.assertEqual(code, 0)
        self.assertIn("alpha", out)
        self.assertIn("beta", out)

    def test_list_all(self):
        self.cli(["create", "Active One"])
        self.cli(["create", "Done One"])
        self.cli(["close", "done-one"])
        out, _, _ = self.cli(["list", "--status", "all"])
        self.assertIn("active-one", out)
        self.assertIn("done-one", out)

    def test_list_completed(self):
        self.cli(["create", "Done"])
        self.cli(["close", "done"])
        out, _, code = self.cli(["list", "--status", "completed"])
        self.assertEqual(code, 0)
        self.assertIn("done", out)


class TestProjectClose(Base):
    def test_close(self):
        self.cli(["create", "Closable"])
        out, _, _ = self.cli(["close", "closable"])
        self.assertIn("Completed", out)

    def test_abandon(self):
        self.cli(["create", "Abandon"])
        out, _, _ = self.cli(["close", "abandon", "--abandon"])
        self.assertIn("Abandoned", out)


class TestProjectRemove(Base):
    def test_remove_project(self):
        self.cli(["create", "Removable"])
        out, _, _ = self.cli(["remove", "removable"])
        self.assertIn("Removed project", out)
        _, _, code = self.cli(["list"])
        self.assertEqual(code, 1)


class TestProjectNote(Base):
    def test_project_note(self):
        self.cli(["create", "Notepad"])
        out, _, _ = self.cli(["note", "notepad", "Some note"])
        self.assertIn("Updated note", out)

    def test_ticket_note(self):
        self.cli(["create", "NP", "--ticket", "Task"])
        self.cli(["note", "np", "Ticket note", "--ticket", "1"])
        c = self.conn()
        row = c.execute("SELECT notes FROM tickets WHERE id=1").fetchone()
        self.assertEqual(row["notes"], "Ticket note")
        c.close()


# ===== Ticket CRUD =====

class TestTicketAdd(Base):
    def test_add(self):
        self.cli(["create", "Proj"])
        out, _, _ = self.cli(["ticket", "add", "proj", "New Task"])
        self.assertIn("Added ticket #", out)

    def test_add_with_deps(self):
        self.cli(["create", "Proj", "--ticket", "First"])
        out, _, _ = self.cli(["ticket", "add", "proj", "Second", "--depends", "1"])
        self.assertIn("Added ticket #2", out)

    def test_add_with_notes(self):
        self.cli(["create", "Proj"])
        self.cli(["ticket", "add", "proj", "Task", "--notes", "Do this carefully"])
        c = self.conn()
        row = c.execute("SELECT notes FROM tickets WHERE id=1").fetchone()
        self.assertEqual(row["notes"], "Do this carefully")
        c.close()

    def test_add_invalid_dep(self):
        self.cli(["create", "Proj"])
        _, err, code = self.cli(["ticket", "add", "proj", "Task", "--depends", "999"])
        self.assertEqual(code, 2)


class TestTicketDone(Base):
    def test_done(self):
        self.cli(["create", "Proj", "--ticket", "Task"])
        out, _, _ = self.cli(["ticket", "done", "proj", "1"])
        self.assertIn("✓", out)
        self.assertIn("done", out)

    def test_done_multiple(self):
        self.cli(["create", "Proj", "--ticket", "A", "--ticket", "B"])
        out, _, _ = self.cli(["ticket", "done", "proj", "1", "2"])
        self.assertEqual(out.count("✓"), 2)

    def test_done_nonexistent(self):
        self.cli(["create", "Proj"])
        _, _, code = self.cli(["ticket", "done", "proj", "999"])
        self.assertEqual(code, 2)


class TestTicketSkip(Base):
    def test_skip(self):
        self.cli(["create", "Proj", "--ticket", "Skipme"])
        out, _, _ = self.cli(["ticket", "skip", "proj", "1"])
        self.assertIn("⊘", out)
        self.assertIn("skipped", out)


class TestTicketStart(Base):
    def test_start(self):
        self.cli(["create", "Proj", "--ticket", "WIP"])
        out, _, _ = self.cli(["ticket", "start", "proj", "1"])
        self.assertIn("▶", out)
        self.assertIn("in-progress", out)


class TestTicketList(Base):
    def test_list_all(self):
        self.cli(["create", "Proj", "--ticket", "A", "--ticket", "B"])
        out, _, code = self.cli(["ticket", "list", "proj"])
        self.assertEqual(code, 0)
        self.assertIn("A", out)
        self.assertIn("B", out)

    def test_list_pending(self):
        self.cli(["create", "Proj", "--ticket", "A", "--ticket", "B"])
        self.cli(["ticket", "done", "proj", "1"])
        out, _, _ = self.cli(["ticket", "list", "proj", "--status", "pending"])
        self.assertNotIn("A", out)  # A is done
        self.assertIn("B", out)

    def test_list_empty(self):
        self.cli(["create", "Proj"])
        _, _, code = self.cli(["ticket", "list", "proj"])
        self.assertEqual(code, 1)


class TestTicketRemove(Base):
    def test_remove_ticket(self):
        self.cli(["create", "Proj", "--ticket", "Gone"])
        out, _, _ = self.cli(["remove", "proj", "--ticket", "1"])
        self.assertIn("Removed ticket", out)

    def test_remove_cleans_deps(self):
        self.cli(["create", "Proj", "--ticket", "A", "--ticket", "B"])
        self.cli(["depend", "proj", "2", "--on", "1"])
        self.cli(["remove", "proj", "--ticket", "1"])
        c = self.conn()
        row = c.execute("SELECT depends_on FROM tickets WHERE id=2").fetchone()
        deps = json.loads(row["depends_on"])
        self.assertEqual(deps, [])
        c.close()


# ===== Dependencies & Next =====

class TestDependencies(Base):
    def test_add_dependency(self):
        self.cli(["create", "Proj", "--ticket", "A", "--ticket", "B"])
        out, _, _ = self.cli(["depend", "proj", "2", "--on", "1"])
        self.assertIn("depends on", out)

    def test_circular_dep_direct(self):
        self.cli(["create", "Proj", "--ticket", "A", "--ticket", "B"])
        self.cli(["depend", "proj", "2", "--on", "1"])
        _, err, code = self.cli(["depend", "proj", "1", "--on", "2"])
        self.assertEqual(code, 2)
        self.assertIn("Circular", err)

    def test_circular_dep_chain(self):
        self.cli(["create", "P", "--ticket", "A", "--ticket", "B", "--ticket", "C"])
        self.cli(["depend", "p", "2", "--on", "1"])
        self.cli(["depend", "p", "3", "--on", "2"])
        _, err, code = self.cli(["depend", "p", "1", "--on", "3"])
        self.assertEqual(code, 2)

    def test_self_dependency(self):
        self.cli(["create", "P", "--ticket", "A"])
        _, err, code = self.cli(["depend", "p", "1", "--on", "1"])
        self.assertEqual(code, 2)

    def test_circular_on_add(self):
        self.cli(["create", "P", "--ticket", "A"])
        # ticket 2 depends on 1, which is fine
        self.cli(["ticket", "add", "p", "B", "--depends", "1"])
        # Now try to make 1 depend on 2
        _, err, code = self.cli(["depend", "p", "1", "--on", "2"])
        self.assertEqual(code, 2)

    def test_merge_deps(self):
        self.cli(["create", "P", "--ticket", "A", "--ticket", "B", "--ticket", "C"])
        self.cli(["depend", "p", "3", "--on", "1"])
        self.cli(["depend", "p", "3", "--on", "2"])
        c = self.conn()
        row = c.execute("SELECT depends_on FROM tickets WHERE id=3").fetchone()
        deps = sorted(json.loads(row["depends_on"]))
        self.assertEqual(deps, [1, 2])
        c.close()


class TestNext(Base):
    def test_next_simple(self):
        self.cli(["create", "P", "--ticket", "Do this"])
        out, _, code = self.cli(["next"])
        self.assertEqual(code, 0)
        self.assertIn("Do this", out)

    def test_next_blocked(self):
        self.cli(["create", "P", "--ticket", "A", "--ticket", "B"])
        self.cli(["depend", "p", "2", "--on", "1"])
        out, _, _ = self.cli(["next"])
        self.assertIn("A", out)
        self.assertNotIn("B", out)

    def test_next_unblocked_after_done(self):
        self.cli(["create", "P", "--ticket", "A", "--ticket", "B"])
        self.cli(["depend", "p", "2", "--on", "1"])
        self.cli(["ticket", "done", "p", "1"])
        out, _, _ = self.cli(["next"])
        self.assertIn("B", out)

    def test_next_shows_in_progress(self):
        self.cli(["create", "P", "--ticket", "WIP"])
        self.cli(["ticket", "start", "p", "1"])
        out, _, _ = self.cli(["next"])
        self.assertIn("WIP", out)
        self.assertIn("▶", out)

    def test_next_no_active(self):
        _, _, code = self.cli(["next"])
        self.assertEqual(code, 1)

    def test_next_all_done(self):
        self.cli(["create", "P", "--ticket", "A"])
        self.cli(["ticket", "done", "p", "1"])
        _, _, code = self.cli(["next"])
        self.assertEqual(code, 1)

    def test_next_specific_project(self):
        self.cli(["create", "Alpha", "--ticket", "Task A"])
        self.cli(["create", "Beta", "--ticket", "Task B"])
        out, _, _ = self.cli(["next", "alpha"])
        self.assertIn("Task A", out)
        self.assertNotIn("Task B", out)

    def test_next_skip_unblocks(self):
        self.cli(["create", "P", "--ticket", "A", "--ticket", "B"])
        self.cli(["depend", "p", "2", "--on", "1"])
        self.cli(["ticket", "skip", "p", "1"])
        out, _, _ = self.cli(["next"])
        self.assertIn("B", out)

    def test_next_multiple_deps(self):
        self.cli(["create", "P", "--ticket", "A", "--ticket", "B", "--ticket", "C"])
        self.cli(["depend", "p", "3", "--on", "1,2"])
        # C blocked on both A and B
        out, _, _ = self.cli(["next"])
        self.assertIn("A", out)
        self.assertIn("B", out)
        self.assertNotIn("C", out)
        # Done A, C still blocked on B
        self.cli(["ticket", "done", "p", "1"])
        out, _, _ = self.cli(["next"])
        self.assertNotIn("C", out)
        # Done B, C unblocked
        self.cli(["ticket", "done", "p", "2"])
        out, _, _ = self.cli(["next"])
        self.assertIn("C", out)


class TestAutoComplete(Base):
    def test_auto_complete_on_done(self):
        self.cli(["create", "P", "--ticket", "Only"])
        out, _, _ = self.cli(["ticket", "done", "p", "1"])
        self.assertIn("auto-completed", out)
        c = self.conn()
        row = c.execute("SELECT status FROM projects WHERE slug='p'").fetchone()
        self.assertEqual(row["status"], "completed")
        c.close()

    def test_auto_complete_on_skip(self):
        self.cli(["create", "P", "--ticket", "A", "--ticket", "B"])
        self.cli(["ticket", "done", "p", "1"])
        self.cli(["ticket", "skip", "p", "2"])
        c = self.conn()
        row = c.execute("SELECT status FROM projects WHERE slug='p'").fetchone()
        self.assertEqual(row["status"], "completed")
        c.close()

    def test_no_auto_complete_partial(self):
        self.cli(["create", "P", "--ticket", "A", "--ticket", "B"])
        self.cli(["ticket", "done", "p", "1"])
        c = self.conn()
        row = c.execute("SELECT status FROM projects WHERE slug='p'").fetchone()
        self.assertEqual(row["status"], "active")
        c.close()


# ===== Attachments & Log =====

class TestAttachments(Base):
    def test_attach_url(self):
        self.cli(["create", "P"])
        out, _, _ = self.cli(["attach", "p", "Repo", "https://github.com/example"])
        self.assertIn("Attached", out)

    def test_attach_path(self):
        self.cli(["create", "P"])
        out, _, _ = self.cli(["attach", "p", "Design", "/tmp/design.md"])
        self.assertIn("Attached", out)

    def test_attach_to_ticket(self):
        self.cli(["create", "P", "--ticket", "T"])
        self.cli(["attach", "p", "Ref", "https://example.com", "--ticket", "1"])
        c = self.conn()
        row = c.execute("SELECT ticket_id FROM attachments WHERE label='Ref'").fetchone()
        self.assertEqual(row["ticket_id"], 1)
        c.close()

    def test_attach_invalid_ticket(self):
        self.cli(["create", "P"])
        _, _, code = self.cli(["attach", "p", "Bad", "file.txt", "--ticket", "999"])
        self.assertEqual(code, 2)


class TestLog(Base):
    def test_log_entry(self):
        self.cli(["create", "P"])
        out, _, _ = self.cli(["log", "p", "Did something"])
        self.assertIn("Logged", out)

    def test_log_with_ticket(self):
        self.cli(["create", "P", "--ticket", "T"])
        self.cli(["log", "p", "Progress on T", "--ticket", "1"])
        c = self.conn()
        row = c.execute("SELECT ticket_id FROM log WHERE entry='Progress on T'").fetchone()
        self.assertEqual(row["ticket_id"], 1)
        c.close()

    def test_log_invalid_ticket(self):
        self.cli(["create", "P"])
        _, _, code = self.cli(["log", "p", "Bad", "--ticket", "999"])
        self.assertEqual(code, 2)


# ===== Output Formats =====

class TestStatusFormats(Base):
    def _setup_project(self):
        self.cli(["create", "Demo", "--ticket", "First", "--ticket", "Second", "--ticket", "Third"])
        self.cli(["depend", "demo", "3", "--on", "1"])
        self.cli(["ticket", "done", "demo", "1"])
        self.cli(["ticket", "start", "demo", "2"])

    def test_full_format(self):
        self._setup_project()
        out, _, _ = self.cli(["status", "demo"])
        self.assertIn("Demo [active]", out)
        self.assertIn("1/3 done", out)
        self.assertIn("✓", out)
        self.assertIn("▶", out)

    def test_compact_format(self):
        self._setup_project()
        out, _, _ = self.cli(["status", "demo", "--format", "compact"])
        self.assertIn("📋", out)
        self.assertIn("1/3 done", out)

    def test_json_format(self):
        self._setup_project()
        out, _, _ = self.cli(["status", "demo", "--format", "json"])
        data = json.loads(out)
        self.assertEqual(data["slug"], "demo")
        self.assertEqual(data["done"], 1)
        self.assertEqual(data["total"], 3)
        self.assertEqual(len(data["tickets"]), 3)

    def test_full_shows_attachments(self):
        self.cli(["create", "P", "--ticket", "T"])
        self.cli(["attach", "p", "Doc", "https://example.com"])
        out, _, _ = self.cli(["status", "p"])
        self.assertIn("📎", out)
        self.assertIn("Doc", out)

    def test_full_shows_log(self):
        self.cli(["create", "P", "--ticket", "T"])
        self.cli(["log", "p", "Made progress"])
        out, _, _ = self.cli(["status", "p"])
        self.assertIn("📝", out)
        self.assertIn("Made progress", out)

    def test_full_shows_blocked(self):
        self.cli(["create", "P", "--ticket", "A", "--ticket", "B"])
        self.cli(["depend", "p", "2", "--on", "1"])
        out, _, _ = self.cli(["status", "p"])
        self.assertIn("blocked", out)
        self.assertIn("waiting on 1", out)

    def test_status_all_active(self):
        self.cli(["create", "A", "--ticket", "T1"])
        self.cli(["create", "B", "--ticket", "T2"])
        out, _, _ = self.cli(["status"])
        self.assertIn("A", out)
        self.assertIn("B", out)

    def test_status_no_active(self):
        _, _, code = self.cli(["status"])
        self.assertEqual(code, 1)


# ===== Edge Cases =====

class TestEdgeCases(Base):
    def test_resolve_by_id(self):
        self.cli(["create", "My Project"])
        out, _, _ = self.cli(["status", "1"])
        self.assertIn("My Project", out)

    def test_resolve_missing(self):
        _, _, code = self.cli(["status", "nonexistent"])
        self.assertEqual(code, 2)

    def test_slugify_empty_after_strip(self):
        out, _, _ = self.cli(["create", "!@#$%"])
        self.assertIn("project", out)

    def test_env_var_override(self):
        alt_dir = tempfile.mkdtemp()
        alt_db = os.path.join(alt_dir, "alt.db")
        os.environ["AGENTPLAN_DB"] = alt_db
        os.environ["AGENTPLAN_DIR"] = alt_dir
        self.cli(["init"])
        self.assertTrue(os.path.exists(alt_db))
        os.unlink(alt_db)
        for ext in ["-wal", "-shm"]:
            p = alt_db + ext
            if os.path.exists(p):
                os.unlink(p)
        os.rmdir(alt_dir)
        # Restore
        os.environ["AGENTPLAN_DB"] = self.db_path
        os.environ["AGENTPLAN_DIR"] = self.tmpdir

    def test_project_no_tickets(self):
        self.cli(["create", "Empty"])
        out, _, _ = self.cli(["status", "empty"])
        self.assertIn("0/0 done", out)

    def test_done_on_closed_project(self):
        """Marking tickets done on a closed project doesn't re-open it."""
        self.cli(["create", "P", "--ticket", "A", "--ticket", "B"])
        self.cli(["close", "p"])
        self.cli(["ticket", "done", "p", "1"])
        c = self.conn()
        row = c.execute("SELECT status FROM projects WHERE slug='p'").fetchone()
        self.assertEqual(row["status"], "completed")  # stays completed
        c.close()

    def test_long_title_slug(self):
        title = "A" * 100
        self.cli(["create", title])
        c = self.conn()
        row = c.execute("SELECT slug FROM projects").fetchone()
        self.assertLessEqual(len(row["slug"]), 60)
        c.close()


# ===== CLI Parsing =====

class TestCLIParsing(Base):
    def test_version_command(self):
        out, _, _ = self.cli(["version"])
        self.assertIn("0.1.1", out)

    def test_version_flag(self):
        _, _, code = self.cli(["--version"])
        # argparse prints version and exits with 0
        self.assertEqual(code, 0)

    def test_no_args(self):
        _, _, code = self.cli([])
        self.assertEqual(code, 2)

    def test_init(self):
        out, _, code = self.cli(["init"])
        self.assertEqual(code, 0)
        self.assertIn("Initialized", out)


# ===== Slugify Unit Tests =====

class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(agentplan.slugify("Hello World"), "hello-world")

    def test_special_chars(self):
        self.assertEqual(agentplan.slugify("Test @#$ Project!"), "test-project")

    def test_hyphens_preserved(self):
        self.assertEqual(agentplan.slugify("my-project"), "my-project")

    def test_max_length(self):
        self.assertLessEqual(len(agentplan.slugify("a" * 100)), 60)

    def test_empty_result(self):
        self.assertEqual(agentplan.slugify("!@#"), "project")


if __name__ == "__main__":
    unittest.main()

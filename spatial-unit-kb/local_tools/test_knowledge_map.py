import tempfile
import threading
import json
import unittest
from pathlib import Path
from urllib.request import urlopen
from knowledge_map import KnowledgeMap
from route_viewer import make_server


class KnowledgeMapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.map = KnowledgeMap(self.root)
        (self.root / "note.md").write_text("Synthetic", encoding="utf-8")

    def source(self, version=0):
        return self.map.lib.register_source("SRC-A", "note.md", "Example", "user_note", expected_version=version)

    def test_empty_read_does_not_create_database(self):
        self.assertEqual(self.map.graph()["nodes"], [])
        self.assertFalse(self.map.lib.db.exists())

    def test_classification_revision_and_namespace(self):
        self.source()
        ref = {"id":"SRC-A", "version":1}
        first = self.map.classify(ref, ["Statistics", "Statistics", "Methods"], "Teaching categorization")
        self.assertEqual(len(self.map.graph()["domains"]), 2)
        with self.assertRaises(ValueError):
            self.map.classify(ref, ["Changed"], "Conflict")
        self.map.classify(ref, [], "Remove labels", 1)
        self.assertEqual(self.map.graph()["domains"], [])
        self.assertEqual(self.map.lib.get(first["id"],1)["data"]["domains"], ["Methods", "Statistics"])
        self.assertEqual(KnowledgeMap(self.root,"demo").graph()["nodes"], [])
        with self.assertRaises(ValueError):
            self.map.classify({"id":"MISSING","version":1}, ["X"], "Reason")

    def test_exact_versions_and_no_silent_inheritance(self):
        self.source()
        self.map.classify({"id":"SRC-A","version":1}, ["Statistics"], "Reason")
        self.map.lib.save_card("METHOD-A", "method", {
            "title":"Mean","content":"Synthetic","conditions":"Teaching","limitations":"No evidence",
            "basis":"direct","rationale":"Teaching","procedure":"Read"
        }, [{"id":"SRC-A","version":1}])
        self.source(1)
        graph = self.map.graph()
        nodes = {n["uid"]:n for n in graph["nodes"]}
        self.assertTrue(nodes["SRC-A@1"]["historical"])
        self.assertEqual(nodes["SRC-A@2"]["domains"], [])
        self.assertIn({"from":"METHOD-A@1","to":"SRC-A@1","relation":"references"}, graph["edges"])

    def test_revision_changes_on_new_record_and_http(self):
        server = make_server(self.root,0)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = "http://127.0.0.1:" + str(server.server_port)
        def get(path):
            with urlopen(base+path) as response:
                return response.read()
        before = json.loads(get("/api/knowledge-graph"))["revision"]
        self.source()
        after = json.loads(get("/api/knowledge-graph"))
        self.assertNotEqual(before,after["revision"])
        self.assertEqual(after["revision"],self.map.graph()["revision"])
        for path in ("/knowledge","/knowledge.js","/knowledge.css"):
            self.assertTrue(get(path))
        self.assertEqual(json.loads(get("/api/knowledge-graph?namespace=demo"))["nodes"],[])

    def test_graph_does_not_truncate_at_search_limit(self):
        with self.map.lib.connection(True) as conn:
            for i in range(251):
                self.map.lib._save(conn,"METHOD-"+str(i),"method",{"title":"Synthetic"},[],0)
        self.assertEqual(len(self.map.graph()["nodes"]),251)

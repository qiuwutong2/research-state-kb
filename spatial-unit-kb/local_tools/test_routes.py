import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import urlopen, Request
from urllib.error import HTTPError

from routes import Routes
from route_viewer import make_server


def node():
    return {"experiment_id":"EX-1","title":"Initial","stage":"start","status":"planned","goal":"Test goal",
            "method":"Method A","rationale":"Synthetic note","parameters":{"alpha":0.1,"remove_me":True},
            "parents":[],"knowledge":[{"id":"SRC-1","version":1}],"datasets":[],"artifacts":[],
            "change_reason":"Initial plan","summary":"Not executed","open_questions":"Unknown"}


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.r=Routes(self.root)
        self.path=self.root/"note.md"
        self.path.write_text("Synthetic source",encoding="utf-8")
        self.r.lib.register_source("SRC-1","note.md","Example","user_note","Test author")
        self.a=node()
        self.r.append("NODE-A",self.a)

    def child(self):
        b=copy.deepcopy(self.a)
        b.update(title="Child",stage="middle",parents=[{"id":"NODE-A","version":1}],change_reason="Parameter change")
        return b

    def test_append_only_branches_and_merge(self):
        b=self.child();self.r.append("NODE-B",b)
        c=self.child();c["title"]="Other branch";self.r.append("NODE-C",c)
        d=self.child();d["parents"]=[{"id":"NODE-B","version":1},{"id":"NODE-C","version":1}]
        self.r.append("NODE-D",d)
        graph=self.r.graph("EX-1")
        self.assertEqual(len(graph["nodes"]),4)
        self.assertEqual(len(graph["edges"]),4)
        with self.assertRaisesRegex(ValueError,"stale"):
            self.r.append("NODE-A",b)
        self.assertEqual(self.r.lib.get("NODE-A")["data"],self.a)

    def test_missing_parent_cycle_and_cross_experiment_rejected(self):
        b=self.child();b["parents"]=[{"id":"NODE-B","version":1}]
        with self.assertRaises(ValueError): self.r.append("NODE-B",b)
        b=self.child();b["experiment_id"]="EX-2"
        with self.assertRaises(ValueError): self.r.append("NODE-B",b)

    def test_per_key_diff_preserves_null_and_removed(self):
        b=self.child();b["parameters"]={"alpha":0.2,"new_null":None}
        self.r.append("NODE-B",b)
        result=self.r.compare("NODE-A","NODE-B")
        self.assertEqual(result["parameter_changes"]["alpha"]["after"],0.2)
        self.assertFalse(result["parameter_changes"]["remove_me"]["after_present"])
        self.assertTrue(result["parameter_changes"]["new_null"]["after_present"])

    def test_new_sources_data_versions_and_fixed_old_node(self):
        self.path.write_text("Revised note",encoding="utf-8")
        self.r.lib.register_source("SRC-1","note.md","Example v2","user_note",expected_version=1)
        data=self.root/"data.csv";data.write_text("x\n1\n")
        self.r.register_file("DATA-1","data.csv","Dataset","dataset","Synthetic")
        b=self.child();b["knowledge"]=[{"id":"SRC-1","version":2}];b["datasets"]=[{"id":"DATA-1","version":1}]
        self.r.append("NODE-B",b)
        diff=self.r.compare("NODE-A","NODE-B")
        self.assertEqual(diff["reference_changes"]["knowledge"]["added"],b["knowledge"])
        self.assertEqual(self.r.lib.get("NODE-A")["data"]["knowledge"][0]["version"],1)

    def test_complete_requires_artifact_and_does_not_certify_run(self):
        b=self.child();b["status"]="completed"
        with self.assertRaises(ValueError): self.r.append("NODE-B",b)
        log=self.root/"result.log";log.write_text("Synthetic report. No run.")
        saved=self.r.register_file("OUT-1","result.log","Output","artifact","Synthetic fixture")
        b["artifacts"]=[{"id":"OUT-1","version":1}]
        self.r.append("NODE-B",b)
        self.assertEqual(self.r.lib.get("NODE-B")["record_status"],"reported_not_independently_verified")
        self.assertFalse((self.root/"spatial-unit-kb/data/real_summary").exists())

    def test_wrong_roles_namespace_and_no_basis(self):
        d=self.root/"data.csv";d.write_text("x\n1\n")
        self.r.register_file("DATA-1","data.csv","Data","dataset","Synthetic")
        b=self.child();b["artifacts"]=[{"id":"DATA-1","version":1}]
        with self.assertRaises(ValueError): self.r.append("NODE-B",b)
        b=self.child();b["knowledge"]=[]
        with self.assertRaises(ValueError): self.r.append("NODE-B",b)
        with self.assertRaises(ValueError): Routes(self.root,"demo").append("NODE-X",self.a)

    def test_file_revision_and_tamper_detection(self):
        p=self.root/"data.json";p.write_text('{"x":1}')
        self.r.register_file("DATA-1","data.json","Data","dataset","Synthetic")
        old=self.r.lib.trace("DATA-1")["files"][0]
        p.write_text('{"x":2}')
        self.r.register_file("DATA-1","data.json","Data","dataset","Synthetic",1)
        self.assertEqual(self.r.lib.trace("DATA-1",1)["files"][0]["sha256"],old["sha256"])
        Path(old["path"]).write_text("tampered")
        with self.assertRaises(ValueError): self.r.lib.trace("DATA-1",1)

    def test_graph_includes_all_beyond_search_limit(self):
        for i in range(251):
            b=self.child();self.r.append("N-"+str(i),b)
        self.assertEqual(len(self.r.graph("EX-1")["nodes"]),252)

    def test_empty_graph_read_does_not_create_store(self):
        root=self.root/"empty"
        self.assertEqual(Routes(root).graph()["nodes"],[])
        self.assertFalse(root.exists())


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        (self.root/"note.html").write_text("<script>alert('unsafe')</script>",encoding="utf-8")
        r=Routes(self.root)
        r.lib.register_source("SRC-1","note.html","Unsafe source test","user_note")
        r.append("NODE-A",node())
        self.server=make_server(self.root,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url="http://127.0.0.1:"+str(self.server.server_port)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=3);self.tmp.cleanup()

    def test_graph_assets_namespace_and_escaped_preview(self):
        with urlopen(self.url+"/api/graph") as r:
            self.assertEqual(len(json.load(r)["nodes"]),1)
        with urlopen(self.url+"/api/graph?namespace=demo") as r:
            self.assertEqual(json.load(r)["nodes"],[])
        with urlopen(self.url+"/") as r:
            self.assertIn("研究脉络",r.read().decode())
            self.assertIn("frame-ancestors 'self'",r.headers["Content-Security-Policy"])
        with urlopen(self.url+"/api/file?id=SRC-1&version=1") as r:
            self.assertTrue(r.headers["Content-Type"].startswith("text/plain"))
            self.assertIn(b"<script>",r.read())  # inert text, not an HTML document
        for name in ("/app.js","/style.css"):
            with urlopen(self.url+name) as r: self.assertEqual(r.status,200)

    def test_denies_write_unknown_paths_and_foreign_host(self):
        for req,expected in [(Request(self.url+"/api/graph",data=b"{}"),405),
                             (Request(self.url+"/",headers={"Host":"evil.example"}),403),
                             (Request(self.url+"/../../library.sqlite3"),404),
                             (Request(self.url+"/api/file?id=SRC-1&version=bad"),400)]:
            with self.assertRaises(HTTPError) as e: urlopen(req)
            self.assertEqual(e.exception.code,expected)
        with self.assertRaises(HTTPError) as e: urlopen(self.url+"/api/graph?namespace=../real")
        self.assertEqual(e.exception.code,400)


if __name__=="__main__":
    unittest.main()

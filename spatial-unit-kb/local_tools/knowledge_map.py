"""Version-aware knowledge graph. Classification is reported metadata, not inference."""
import hashlib
from library import Library, KINDS, require, nonempty, encoded


class KnowledgeMap:
    def __init__(self, workspace, namespace="real"):
        self.lib = Library(workspace, namespace)

    def classify(self, target, domains, rationale, expected_version=0):
        require(isinstance(domains, list) and len(domains) <= 20, "domains must be a list of at most 20 labels")
        require(all(nonempty(d) and len(d.strip()) <= 80 for d in domains), "invalid domain label")
        domains = sorted(set(d.strip() for d in domains))
        require(nonempty(rationale), "classification rationale required")
        with self.lib.connection(True) as conn:
            self.lib._references(conn, [target], KINDS - {"classification"})
            ident = "CLASS-" + hashlib.sha256(encoded(target).encode()).hexdigest()[:32].upper()
            return self.lib._save(conn, ident, "classification",
                                  {"title": "Domain classification", "domains": domains, "rationale": rationale},
                                  [target], expected_version)

    def graph(self):
        if not self.lib.db.exists():
            return {"namespace": self.lib.namespace, "revision": "empty", "nodes": [], "edges": [], "domains": []}
        with self.lib.connection() as conn:
            rows = conn.execute("SELECT r.body,r.checksum FROM records r JOIN (SELECT id,MAX(version) v FROM records GROUP BY id) x ON r.id=x.id AND r.version=x.v ORDER BY r.id").fetchall()
            latest = [self.lib.decode(row) for row in rows]
            latest_versions = {r["id"]: r["version"] for r in latest}
            classifications = { (r["refs"][0]["id"], r["refs"][0]["version"]): r
                                for r in latest if r["kind"] == "classification"}
            pending = [r for r in latest if r["kind"] != "classification"]
            records = {}
            while pending:
                record = pending.pop()
                key = (record["id"], record["version"])
                if key in records:
                    continue
                records[key] = record
                pending.extend(self.lib._get(conn, ref["id"], ref["version"]) for ref in record["refs"])
        nodes, edges, counts = [], [], {}
        for key, record in sorted(records.items()):
            classification = classifications.get(key)
            domains = classification["data"]["domains"] if classification else []
            for domain in domains:
                counts[domain] = counts.get(domain, 0) + 1
            uid = record["id"] + "@" + str(record["version"])
            nodes.append({**record, "uid": uid, "domains": domains,
                          "classification": classification,
                          "historical": latest_versions[record["id"]] != record["version"]})
            for ref in record["refs"]:
                edges.append({"from": uid, "to": ref["id"] + "@" + str(ref["version"]), "relation": "references"})
        result = {"namespace": self.lib.namespace, "nodes": nodes, "edges": edges,
                  "domains": [{"name": name, "count": count} for name, count in sorted(counts.items())]}
        result["revision"] = hashlib.sha256(encoded(result).encode()).hexdigest()
        return result

var out = [];
var tp = function (v) { if (v === null) return "null"; if (Array.isArray(v)) return "array"; if (v instanceof ObjectId) return "objectId"; if (v instanceof Date) return "date"; return typeof v; };
db.getMongo().getDBNames().forEach(function (dn) {
  if (["admin", "config", "local"].indexOf(dn) >= 0) return;
  var d = db.getSiblingDB(dn);
  d.getCollectionNames().forEach(function (cn) {
    var c = d.getCollection(cn), fields = {};
    c.find().limit(30).forEach(function (doc) { Object.keys(doc).forEach(function (k) { var t = tp(doc[k]); fields[k] = fields[k] && fields[k] !== t ? "mixed" : t; }); });
    out.push({ db: dn, collection: cn, count: c.estimatedDocumentCount ? c.estimatedDocumentCount() : c.count(), fields: Object.keys(fields).sort().map(function (k) { return { name: k, type: fields[k] }; }) });
  });
});
print(JSON.stringify(out));

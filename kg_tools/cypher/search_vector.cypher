// Nearest nodes by meaning. $index is one of the emb_<Label> vector indexes (validated in tools.py).
CALL db.index.vector.queryNodes($index, $limit, $vector) YIELD node AS n, score
RETURN n.identifier AS id, labels(n)[0] AS label, n.statementCode AS code, n.name AS name,
       n.description AS description, n.gradeLevel AS grade_level,
       n.jurisdiction AS jurisdiction, n.academicSubject AS subject,
       score
ORDER BY score DESC

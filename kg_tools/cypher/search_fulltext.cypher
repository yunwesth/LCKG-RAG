// Keyword search over name and description (full-text index kg_search).
// $label is optional; when set only nodes with that label are returned.
CALL db.index.fulltext.queryNodes('kg_search', $query) YIELD node AS n, score
WHERE $label IS NULL OR $label IN labels(n)
RETURN n.identifier AS id, labels(n)[0] AS label, n.statementCode AS code, n.name AS name,
       n.description AS description, n.gradeLevel AS grade_level,
       n.jurisdiction AS jurisdiction, n.academicSubject AS subject,
       score
ORDER BY score DESC
LIMIT $limit

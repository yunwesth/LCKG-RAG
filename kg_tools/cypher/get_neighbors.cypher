// Directly connected nodes. $rel is an optional relationship type, $direction is out, in or both
// (both validated in tools.py).
MATCH (n {identifier: $id})-[r]-(m)
WHERE ($rel IS NULL OR type(r) = $rel)
  AND ($direction = 'both'
       OR ($direction = 'out' AND startNode(r) = n)
       OR ($direction = 'in' AND endNode(r) = n))
RETURN type(r) AS rel,
       CASE WHEN startNode(r) = n THEN 'out' ELSE 'in' END AS direction,
       m.identifier AS id, labels(m)[0] AS label, m.statementCode AS code, m.name AS name,
       m.description AS description, m.gradeLevel AS grade_level,
       m.jurisdiction AS jurisdiction, m.academicSubject AS subject
LIMIT $limit

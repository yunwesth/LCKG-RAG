// StandardsFrameworkItem by statement code (for example 8.EE.C.8). Codes repeat across
// jurisdictions, so the optional $jurisdiction narrows the match. Uses idx_item_code.
MATCH (n:StandardsFrameworkItem)
WHERE n.statementCode = $code
  AND ($jurisdiction IS NULL OR n.jurisdiction = $jurisdiction)
RETURN n.identifier AS id, labels(n)[0] AS label, n.statementCode AS code, n.name AS name,
       n.description AS description, n.gradeLevel AS grade_level,
       n.jurisdiction AS jurisdiction, n.academicSubject AS subject
LIMIT $limit

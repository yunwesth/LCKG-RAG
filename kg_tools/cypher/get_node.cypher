// One node by its identifier. Returns zero rows if the id does not exist.
MATCH (n {identifier: $id})
RETURN n.identifier AS id, labels(n)[0] AS label, n.statementCode AS code, n.name AS name,
       n.description AS description, n.gradeLevel AS grade_level,
       n.jurisdiction AS jurisdiction, n.academicSubject AS subject
LIMIT 1

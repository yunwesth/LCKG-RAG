// Standards that build towards the given standard, up to $max_depth hops back.
// Direction (checked 2026-11-17: source grade is earlier in 354 edges, later in 16, equal in 387): (earlier)-[:buildsTowards]->(later), so the nodes on the
// start side of the edge are the prerequisites. $distance is the shortest hop count.
MATCH p = (n:StandardsFrameworkItem)-[:buildsTowards*1..6]->(s:StandardsFrameworkItem {identifier: $id})
WHERE length(p) <= $max_depth
WITH n, min(length(p)) AS distance
RETURN n.identifier AS id, labels(n)[0] AS label, n.statementCode AS code, n.name AS name,
       n.description AS description, n.gradeLevel AS grade_level,
       n.jurisdiction AS jurisdiction, n.academicSubject AS subject,
       distance
ORDER BY distance, code
LIMIT $limit

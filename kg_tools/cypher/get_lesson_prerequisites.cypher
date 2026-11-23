// Lesson groupings that the given grouping depends on, up to $max_depth hops.
// Direction (checked 2026-11-22: target is in an earlier grade in 46 edges, later in 0, same in 44):
// (dependent)-[:hasDependency]->(prerequisite), the OPPOSITE of buildsTowards. $distance is the shortest hop count.
MATCH p = (s:LessonGrouping {identifier: $id})-[:hasDependency*1..6]->(n:LessonGrouping)
WHERE length(p) <= $max_depth
WITH n, min(length(p)) AS distance
RETURN n.identifier AS id, labels(n)[0] AS label, null AS code, n.name AS name,
       n.description AS description, null AS grade_level,
       null AS jurisdiction, null AS subject,
       distance
ORDER BY distance, name
LIMIT $limit

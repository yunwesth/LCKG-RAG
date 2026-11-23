// Distinct jurisdictions that standards belong to (used to validate a user-supplied jurisdiction).
MATCH (n:StandardsFrameworkItem)
WHERE n.jurisdiction IS NOT NULL
RETURN DISTINCT n.jurisdiction AS jurisdiction
ORDER BY jurisdiction
LIMIT 200

"""Names shared by more than one module. Kept here so `ingest` (writer) and `kg_tools` (reader)
agree without importing each other."""

# Label of the single bookkeeping node ingest writes (embedding model + dimension, masterplan Phase 2).
# It is not KG data, so schema checks must ignore it.
INGEST_META_LABEL = "_IngestMeta"
EMBEDDING_PROPERTY = "embedding"

# Parameterized Cypher

One `.cypher` file per query, read-only, parameters only (`$param`), never string-built. Loaded via
`kg_tools.queries.load_query("<name>")` (or `Neo4jReader.read_file`) and checked by `cypher_guard`.

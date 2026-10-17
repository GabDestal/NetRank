# Query benchmarks (PROFILE before / after)

`make benchmark` (`scripts/benchmark.py`) runs three queries with `PROFILE`, once the slow way and once
the way the project does it, and checks that both versions return exactly the same rows.

- **Index cases:** the "before" run drops the index, profiles the query, then recreates the whole schema
  with `apply_schema` (in a `finally`). If the script is stopped halfway, `make schema` puts it back.
  Only run it on your own local database.
- **Rewrite case:** the naive query and the rewritten one are both profiled. No schema change.
- Each query runs 2 times to warm up, then 5 measured times. The time is the median of
  `result_available_after + result_consumed_after` reported by the server.

Setup: Neo4j 5.26.32 Community in Docker (1 GB heap, 512 MB page cache), full data loaded
(1,745 CVEs, 3,599 products). Run on 2026-10-17.

## Results

| Query | Version | db hits | rows | median ms (run 1) | median ms (run 2) |
|---|---|---:|---:|---:|---:|
| CVSS range | before: no index | 4,053 | 20 | 6 | 1 |
| CVSS range | after: `cve_cvss_score` range index | 147 | 20 | 3 | 1 |
| Product lookup | before: no constraint | 7,200 | 1 | 10 | 1 |
| Product lookup | after: `product_product_key` unique index | 3 | 1 | 2 | 1 |
| Exposure groups (3 hops) | before: one long MATCH | 185,838 | 10 | 102 | 19 |
| Exposure groups (3 hops) | after: distinct techniques first | 15,987 | 10 | 7 | 2 |

The db hits are the number to look at: they are the same on every run. Times are in milliseconds and
move a lot between runs (run 2 came right after run 1, with plans and pages already cached), because the graph is
small. On a graph this size, every query is fast in absolute terms; the db hits show how each one would grow.

## 1. CVSS range (D8)

```cypher
MATCH (c:CVE) WHERE c.cvss_score >= $min_score     // $min_score = 9.8, 562 CVEs match
RETURN c.cve_id AS cve_id, c.cvss_score AS score ORDER BY score DESC, cve_id LIMIT 20
```

| | Plan |
|---|---|
| before | `NodeByLabelScan > Filter > Projection > Top > ProduceResults` |
| after | `NodeIndexSeekByRange > Projection > PartialTop > ProduceResults` |

**Why the plan changed:** with the range index, Neo4j reads only the CVEs at or above 9.8, already sorted by
score, so `PartialTop` can stop after the first 20 (plus ties); without it, it reads every CVE, filters
them and sorts all the matches.

## 2. Product lookup (D10, question 7's entry point)

```cypher
MATCH (p:Product {product_key: $product_key})       // 'fortinet:fortios'
RETURN p.product_key AS product_key, p.name AS name
```

| | Plan |
|---|---|
| before | `NodeByLabelScan > Filter > Projection > ProduceResults` |
| after | `NodeUniqueIndexSeek > Projection > ProduceResults` |

**Why the plan changed:** the uniqueness constraint comes with an index, so finding one product is a
seek (O(log n), 3 db hits) instead of reading and comparing all 3,599 products (7,200 db hits).
Every endpoint that starts from an id (group, technique, CVE, product) relies on this.

## 3. Exposure groups, product → CVE → technique ← group (question 7)

Before, written as one long pattern:

```cypher
MATCH (:Product {product_key: $product_key})<-[:AFFECTS]-(:CVE)
      -[:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->(t:Technique)<-[:USES]-(g:Group)
WITH g, count(DISTINCT t) AS shared
ORDER BY shared DESC, g.name LIMIT 10
RETURN g.attack_id AS group_id, shared
```

After, the way `EXPOSURE_QUERY` in `app/services/products.py` does it:

```cypher
MATCH (p:Product {product_key: $product_key})
UNWIND COLLECT { MATCH (p)<-[:AFFECTS]-(:CVE)-[:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->(t:Technique)
                 RETURN DISTINCT t } AS t
MATCH (t)<-[:USES]-(g:Group)
WITH g, count(t) AS shared
ORDER BY shared DESC, g.name LIMIT 10
RETURN g.attack_id AS group_id, shared
```

Measured on `cisco:ios`, the product with the most `AFFECTS` relationships: 1,973 of them (one per NVD
`cpeMatch`, so many per CVE), giving 2,030 product → CVE → technique paths but only 6 distinct techniques.

| | Plan |
|---|---|
| before | `NodeUniqueIndexSeek > Expand(All) > Filter > Expand(All) > Filter > Expand(All) > Filter > EagerAggregation > Top ...` |
| after | `NodeUniqueIndexSeek > Expand(All) > Filter > Expand(All) > Filter > Distinct > RollUpApply > Unwind > Expand(All) > Filter > EagerAggregation > Top ...` |

**Why the plan changed:** the `Distinct` step reduces the 2,030 paths to 6 techniques before the
`USES` expansion, so each technique's groups are read once instead of once per path (11.6x fewer db hits).
Both versions start with the same index seek; the cost difference is only in when duplicates are removed.

## Reproduce

```bash
make docker-run   # if the stack is not up
make benchmark    # prints the table and the plans; the schema is restored at the end
make schema       # optional check: "schema ready: 18 constraints and indexes"
```

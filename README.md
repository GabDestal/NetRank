# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/GabDestal/NetRank/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                          |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|------------------------------ | -------: | -------: | -------: | -------: | ------: | --------: |
| app/\_\_init\_\_.py           |        1 |        0 |        0 |        0 |    100% |           |
| app/agent/\_\_init\_\_.py     |        0 |        0 |        0 |        0 |    100% |           |
| app/agent/graph.py            |      109 |        0 |       26 |        0 |    100% |           |
| app/agent/guardrails.py       |       99 |        4 |       22 |        1 |     96% |137-138, 143-\>145, 176-177 |
| app/agent/llm.py              |      105 |        3 |       22 |        4 |     94% |44, 100, 150-\>160, 168 |
| app/agent/replay.py           |       45 |        6 |        8 |        0 |     89% |46, 76-78, 84-85 |
| app/agent/schema.py           |       65 |        0 |        6 |        0 |    100% |           |
| app/agent/tools.py            |      162 |        4 |       46 |        5 |     96% |169-\>171, 211, 285, 299-\>306, 314, 375 |
| app/agent/verifier.py         |       71 |        1 |       30 |        1 |     98% |        37 |
| app/config.py                 |       21 |        0 |        0 |        0 |    100% |           |
| app/database/\_\_init\_\_.py  |        0 |        0 |        0 |        0 |    100% |           |
| app/database/client.py        |       55 |        2 |       10 |        1 |     95% |   62, 106 |
| app/errors.py                 |        3 |        0 |        0 |        0 |    100% |           |
| app/main.py                   |       43 |        0 |        0 |        0 |    100% |           |
| app/ml/\_\_init\_\_.py        |        0 |        0 |        0 |        0 |    100% |           |
| app/ml/features.py            |       62 |        0 |        6 |        1 |     99% | 86-\>exit |
| app/ml/model.py               |       38 |        0 |        6 |        1 |     98% |   68-\>71 |
| app/models/\_\_init\_\_.py    |        0 |        0 |        0 |        0 |    100% |           |
| app/models/analytics.py       |       23 |        0 |        0 |        0 |    100% |           |
| app/models/common.py          |       12 |        0 |        0 |        0 |    100% |           |
| app/models/graph.py           |       13 |        0 |        0 |        0 |    100% |           |
| app/models/health.py          |        7 |        0 |        0 |        0 |    100% |           |
| app/models/players.py         |       22 |        0 |        0 |        0 |    100% |           |
| app/models/predict.py         |       16 |        0 |        0 |        0 |    100% |           |
| app/routers/\_\_init\_\_.py   |        0 |        0 |        0 |        0 |    100% |           |
| app/routers/agent.py          |       13 |        0 |        0 |        0 |    100% |           |
| app/routers/analytics.py      |       32 |        0 |        0 |        0 |    100% |           |
| app/routers/graph.py          |       15 |        0 |        0 |        0 |    100% |           |
| app/routers/health.py         |       19 |        0 |        2 |        0 |    100% |           |
| app/routers/params.py         |       17 |        0 |        2 |        0 |    100% |           |
| app/routers/players.py        |       23 |        0 |        0 |        0 |    100% |           |
| app/routers/predict.py        |       12 |        0 |        0 |        0 |    100% |           |
| app/security.py               |       16 |        0 |        6 |        0 |    100% |           |
| app/services/\_\_init\_\_.py  |        0 |        0 |        0 |        0 |    100% |           |
| app/services/analytics.py     |      105 |        9 |       36 |        5 |     89% |132, 149, 171-175, 193, 257 |
| app/services/gds.py           |      135 |        3 |       16 |        1 |     97% |246-247, 286 |
| app/services/graph.py         |       40 |        1 |       14 |        1 |     96% |       142 |
| app/services/health.py        |       12 |        0 |        0 |        0 |    100% |           |
| app/services/players.py       |       36 |        0 |        8 |        0 |    100% |           |
| app/services/predict.py       |       71 |       10 |       28 |        3 |     83% |42-48, 58, 66, 69 |
| app/text.py                   |        6 |        0 |        0 |        0 |    100% |           |
| scripts/\_\_init\_\_.py       |        0 |        0 |        0 |        0 |    100% |           |
| scripts/benchmark.py          |       69 |       13 |       16 |        1 |     81% |225-237, 241 |
| scripts/demo\_guardrail.py    |       58 |       27 |       12 |        2 |     50% |34, 41, 67-97, 101 |
| scripts/download\_sackmann.py |       52 |        4 |        8 |        1 |     92% | 44-46, 93 |
| scripts/eval\_agent.py        |      289 |      182 |       88 |       10 |     36% |68, 73-92, 97-103, 111-112, 133, 144-146, 152, 156-158, 167-168, 172-179, 234-270, 282, 292, 297, 302-336, 341-364, 369-404, 409-412, 417-424, 429-443, 448-453, 458-461, 480, 486-513, 529 |
| scripts/gds\_refresh.py       |       13 |       13 |        2 |        0 |      0% |      6-25 |
| scripts/ingest.py             |       69 |       32 |       10 |        2 |     57% |134-143, 158, 166-177, 182-194, 198 |
| scripts/measure\_tokens.py    |       68 |       68 |        8 |        0 |      0% |    11-104 |
| scripts/names.py              |       26 |        1 |        6 |        1 |     94% |        51 |
| scripts/quota\_log.py         |       58 |        4 |        8 |        1 |     92% |114-116, 127 |
| scripts/report.py             |       44 |        0 |        2 |        0 |    100% |           |
| scripts/report\_model.py      |       76 |       20 |       10 |        0 |     77% |102-108, 113-118, 133-193 |
| scripts/resolve.py            |       82 |        0 |       10 |        0 |    100% |           |
| scripts/run\_notebook.py      |       13 |       13 |        2 |        0 |      0% |      6-25 |
| scripts/sackmann.py           |       79 |        2 |       18 |        2 |     96% |   53, 106 |
| scripts/tennis\_data.py       |       59 |        0 |       16 |        1 |     99% |   59-\>61 |
| scripts/train.py              |      136 |       58 |       20 |        2 |     59% |106-\>115, 125, 133, 149, 154-164, 176-177, 185, 190, 200, 205-214, 230-254, 259-279, 283 |
| **TOTAL**                     | **2715** |  **480** |  **530** |   **47** | **81%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/GabDestal/NetRank/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/GabDestal/NetRank/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/GabDestal/NetRank/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/GabDestal/NetRank/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2FGabDestal%2FNetRank%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/GabDestal/NetRank/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.
# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/GabDestal/NetRank/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                          |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|------------------------------ | -------: | -------: | -------: | -------: | ------: | --------: |
| app/\_\_init\_\_.py           |        1 |        0 |        0 |        0 |    100% |           |
| app/agent/\_\_init\_\_.py     |        0 |        0 |        0 |        0 |    100% |           |
| app/config.py                 |       17 |        0 |        0 |        0 |    100% |           |
| app/database/\_\_init\_\_.py  |        0 |        0 |        0 |        0 |    100% |           |
| app/database/client.py        |       36 |        1 |        6 |        0 |     98% |        77 |
| app/errors.py                 |        3 |        0 |        0 |        0 |    100% |           |
| app/main.py                   |       42 |        0 |        0 |        0 |    100% |           |
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
| app/routers/analytics.py      |       32 |        0 |        0 |        0 |    100% |           |
| app/routers/graph.py          |       15 |        0 |        0 |        0 |    100% |           |
| app/routers/health.py         |       19 |        0 |        2 |        0 |    100% |           |
| app/routers/params.py         |       17 |        0 |        2 |        0 |    100% |           |
| app/routers/players.py        |       23 |        0 |        0 |        0 |    100% |           |
| app/routers/predict.py        |       12 |        0 |        0 |        0 |    100% |           |
| app/security.py               |       16 |        0 |        6 |        0 |    100% |           |
| app/services/\_\_init\_\_.py  |        0 |        0 |        0 |        0 |    100% |           |
| app/services/analytics.py     |      105 |        9 |       36 |        5 |     89% |132, 145, 163-167, 185, 247 |
| app/services/gds.py           |      135 |        3 |       16 |        1 |     97% |246-247, 286 |
| app/services/graph.py         |       40 |        1 |       14 |        1 |     96% |       142 |
| app/services/health.py        |       12 |        0 |        0 |        0 |    100% |           |
| app/services/players.py       |       36 |        0 |        8 |        0 |    100% |           |
| app/services/predict.py       |       71 |       10 |       28 |        3 |     83% |42-48, 58, 66, 69 |
| app/text.py                   |        6 |        0 |        0 |        0 |    100% |           |
| scripts/\_\_init\_\_.py       |        0 |        0 |        0 |        0 |    100% |           |
| scripts/benchmark.py          |       69 |       13 |       16 |        1 |     81% |212-224, 228 |
| scripts/download\_sackmann.py |       52 |        4 |        8 |        1 |     92% | 44-46, 93 |
| scripts/gds\_refresh.py       |       13 |       13 |        2 |        0 |      0% |      6-25 |
| scripts/ingest.py             |       69 |       32 |       10 |        2 |     57% |134-143, 158, 166-177, 182-194, 198 |
| scripts/names.py              |       26 |        1 |        6 |        1 |     94% |        51 |
| scripts/report.py             |       44 |        0 |        2 |        0 |    100% |           |
| scripts/report\_model.py      |       76 |       20 |       10 |        0 |     77% |88-94, 99-104, 115-175 |
| scripts/resolve.py            |       82 |        0 |       10 |        0 |    100% |           |
| scripts/sackmann.py           |       79 |        2 |       18 |        2 |     96% |   53, 106 |
| scripts/tennis\_data.py       |       59 |        0 |       16 |        1 |     99% |   59-\>61 |
| scripts/train.py              |      136 |       58 |       20 |        2 |     59% |102-\>111, 121, 129, 145, 150-160, 172-173, 181, 186, 196, 201-210, 226-250, 255-275, 279 |
| **TOTAL**                     | **1536** |  **167** |  **248** |   **22** | **89%** |           |


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
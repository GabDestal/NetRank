# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/GabDestal/NetRank/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                          |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|------------------------------ | -------: | -------: | -------: | -------: | ------: | --------: |
| app/\_\_init\_\_.py           |        1 |        0 |        0 |        0 |    100% |           |
| app/agent/\_\_init\_\_.py     |        0 |        0 |        0 |        0 |    100% |           |
| app/config.py                 |       16 |        0 |        0 |        0 |    100% |           |
| app/database/\_\_init\_\_.py  |        0 |        0 |        0 |        0 |    100% |           |
| app/database/client.py        |       36 |        1 |        6 |        0 |     98% |        77 |
| app/errors.py                 |        3 |        0 |        0 |        0 |    100% |           |
| app/main.py                   |       41 |        0 |        0 |        0 |    100% |           |
| app/models/\_\_init\_\_.py    |        0 |        0 |        0 |        0 |    100% |           |
| app/models/analytics.py       |       23 |        0 |        0 |        0 |    100% |           |
| app/models/common.py          |       12 |        0 |        0 |        0 |    100% |           |
| app/models/graph.py           |       13 |        0 |        0 |        0 |    100% |           |
| app/models/health.py          |        7 |        0 |        0 |        0 |    100% |           |
| app/models/players.py         |       22 |        0 |        0 |        0 |    100% |           |
| app/routers/\_\_init\_\_.py   |        0 |        0 |        0 |        0 |    100% |           |
| app/routers/analytics.py      |       32 |        0 |        0 |        0 |    100% |           |
| app/routers/graph.py          |       15 |        0 |        0 |        0 |    100% |           |
| app/routers/health.py         |       19 |        0 |        2 |        0 |    100% |           |
| app/routers/params.py         |       17 |        0 |        2 |        0 |    100% |           |
| app/routers/players.py        |       23 |        0 |        0 |        0 |    100% |           |
| app/security.py               |       16 |        0 |        6 |        0 |    100% |           |
| app/services/\_\_init\_\_.py  |        0 |        0 |        0 |        0 |    100% |           |
| app/services/analytics.py     |      105 |        9 |       36 |        5 |     89% |132, 145, 163-167, 185, 247 |
| app/services/gds.py           |      132 |        3 |       14 |        1 |     97% |246-247, 277 |
| app/services/graph.py         |       40 |        1 |       14 |        1 |     96% |       142 |
| app/services/health.py        |       12 |        0 |        0 |        0 |    100% |           |
| app/services/players.py       |       36 |        0 |        8 |        0 |    100% |           |
| app/text.py                   |        6 |        0 |        0 |        0 |    100% |           |
| scripts/\_\_init\_\_.py       |        0 |        0 |        0 |        0 |    100% |           |
| scripts/benchmark.py          |       69 |       13 |       16 |        1 |     81% |212-224, 228 |
| scripts/download\_sackmann.py |       52 |        4 |        8 |        1 |     92% | 44-46, 93 |
| scripts/gds\_refresh.py       |       13 |       13 |        2 |        0 |      0% |      6-25 |
| scripts/ingest.py             |       69 |       32 |       10 |        2 |     57% |134-143, 158, 166-177, 182-194, 198 |
| scripts/names.py              |       26 |        1 |        6 |        1 |     94% |        51 |
| scripts/report.py             |       44 |        0 |        2 |        0 |    100% |           |
| scripts/resolve.py            |       82 |        0 |       10 |        0 |    100% |           |
| scripts/sackmann.py           |       79 |        2 |       18 |        2 |     96% |   53, 106 |
| scripts/tennis\_data.py       |       59 |        0 |       16 |        1 |     99% |   59-\>61 |
| **TOTAL**                     | **1120** |   **79** |  **176** |   **15** | **92%** |           |


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
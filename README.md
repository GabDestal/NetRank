# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/GabDestal/NetRank/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                         |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|----------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| app/\_\_init\_\_.py          |        1 |        0 |        0 |        0 |    100% |           |
| app/agent/\_\_init\_\_.py    |        0 |        0 |        0 |        0 |    100% |           |
| app/config.py                |       13 |        0 |        0 |        0 |    100% |           |
| app/database/\_\_init\_\_.py |        0 |        0 |        0 |        0 |    100% |           |
| app/database/client.py       |       25 |        1 |        0 |        0 |     96% |        54 |
| app/main.py                  |       18 |        0 |        0 |        0 |    100% |           |
| app/models/\_\_init\_\_.py   |        0 |        0 |        0 |        0 |    100% |           |
| app/models/health.py         |        7 |        0 |        0 |        0 |    100% |           |
| app/routers/\_\_init\_\_.py  |        0 |        0 |        0 |        0 |    100% |           |
| app/routers/health.py        |       19 |        0 |        2 |        0 |    100% |           |
| app/services/\_\_init\_\_.py |        0 |        0 |        0 |        0 |    100% |           |
| app/services/health.py       |       12 |        0 |        0 |        0 |    100% |           |
| **TOTAL**                    |   **95** |    **1** |    **2** |    **0** | **99%** |           |


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
# Contributing

To change discovery, describe one query or repository case that the current finder gets wrong. Add a small offline fixture and show how the shortlist changes. To add an agent, include its official context documentation, a tested way to supply the workflow and the required credit paragraph. Keep the three language guides aligned when commands or behavior change.

Run the offline suite from the repository root:

```sh
python3 -m unittest discover -s tests -v
python3 skills/repo-neighbor/scripts/quota.py check-pr templates/contribution.md
```

A live smoke check requires an authenticated GitHub CLI and network access. Use a limit of one and record whether GitHub returned a candidate, an empty sample or an error. Do not submit an upstream PR solely to test this finder.

Community proposals and ballots use the [community desk](campaigns/reports/README.md). For credentials use the [encrypted grant flow](sponsorship/README.md). Never put a raw credential in an issue or PR.

# Project workflow

This project uses a lightweight, evidence-based agile workflow. The repository's earlier history
was created in a short period by one contributor; it is not presented as proof of multiple sprints,
reviews, or team ceremonies. The backlog below records current work and gives future changes a
reviewable plan. Update it as work is completed rather than inventing past sprint records.

## Planning

- Keep work in `product-backlog.md`, ordered by priority. Each item has a clear outcome and
  acceptance criteria that can be checked.
- At the start of a work session or iteration, select a small set of items that can be completed
  and demonstrated together. Record the selected IDs, dates, and outcome in the iteration log
  below.
- Reorder or split work when results, risks, or dependencies change; note the reason in the log.

## Implementation and commits

- Make changes in small, coherent increments that produce a working or reviewable result.
- Use commit subjects in the form `type(area): outcome`, for example
  `fix(failover): retry downloads after server loss` or
  `docs(experiments): clarify rerun requirements`.
- Keep each commit focused on one outcome. Avoid `wip` commits in the final shared history; if a
  change needs several steps, make each step understandable or squash it before sharing.
- Do not change old commit dates or authors to make activity look evenly distributed. Commit
  history should reflect when work actually happened.

## Definition of done

An item is done when:

1. Its acceptance criteria are met and the relevant check or demo is recorded.
2. Documentation and expected outputs are updated when behavior or setup changes.
3. The change is committed with a focused, descriptive subject.
4. Any known limitation or follow-up is recorded in the backlog.

If a check cannot be run in the current environment, record that explicitly; do not mark the check
as passing based only on inspection.

## Iteration log

Add one entry when an iteration is actually planned and reviewed. This log intentionally starts
empty so it does not imply ceremonies that have not happened.

| Iteration | Dates | Selected backlog IDs | Outcome / demo | Follow-up |
|---|---|---|---|---|
| _Record the next real iteration here._ | | | | |

## Review notes

At the end of an iteration, briefly record what worked, what blocked progress, and one change to
try next time. Keep the notes factual and dated.

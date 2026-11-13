# Agile test plan

## Purpose and scope

This plan makes each backlog item verifiable in small increments. It covers the TCP client/server,
Ryu controller and selector, Mininet topology and scenarios, and experiment/report pipeline. It does
not treat historical result files as proof that current code passes.

## Test levels

| Level | Focus | Run / evidence | When |
|---|---|---|---|
| Unit and regression | Pure decisions, parsing, route state, retry/checksum behavior, and regressions | `uv run python -m unittest discover -s tests -v` | Every change and before review |
| Static checks | Python syntax and whitespace/errors in the proposed change | `uv run python -m compileall -q app controller topology tests` and `git diff --check` | Every change and before review |
| Scenario integration | Actual controller + OVS/Mininet behavior across hosts and TCP flows | `sudo mn -c`, start Ryu, then `uv run python tests/run_scenarios.py smoke` | Before merging networking/controller changes |
| Resilience and path acceptance | Server failover, path failure/degradation/recovery, checksum continuity | `uv run python tests/run_scenarios.py failover` and `uv run python tests/run_scenarios.py path` in dynamic mode | For changes to heartbeat, flow management, routes, or client retry |
| Load and experiment acceptance | Concurrent clients, congestion selection, static-vs-dynamic measurements | `six-client-smoke`, `adaptive-congestion`, then `experiments --quick` in each mode | For selector, topology, or performance changes; full matrix for release/results |
| Reporting | CSV parsing and generated summaries/figures match the selected run data | `uv run python tests/run_scenarios.py report`; inspect outputs under `results/` | After experiment data/schema changes |

Mininet integration checks require Ubuntu/Linux networking, Mininet, Open vSwitch, and a running
controller. If those prerequisites are unavailable, record the exact blocker and leave the level
unverified; unit tests are not a substitute for network acceptance.

## Acceptance criteria by behavior

- Delivery: request the virtual IP, receive the requested bytes, and verify the expected SHA-256.
- Selection: a new connection selects an available low-cost route; no healthy route is reported
  safely rather than assigned to a dead server.
- Server failure: after heartbeat timeout, new connections avoid the failed server and an active
  download resumes from its last byte; the completed content checksum matches.
- Path failure/degradation: an active srv1 transfer moves to the backup path without reconnecting;
  after recovery, new connections return to the direct path.
- Concurrency/congestion: six independent clients complete simultaneously; adaptive congestion
  demonstrates route/server choice and reports valid checksums.
- Experiments: both modes and all required conditions have identifiable configuration and valid
  measurements; excluded/failed runs are explained, never silently discarded.

Use `tests/expected/` only where a matching expected-output fixture exists; otherwise assert the
behavioral criteria above and retain the command output with the iteration evidence.

## Agile execution loop

1. Select a small backlog item and translate each acceptance criterion into a test or demo.
2. For a defect or new behavior, add a focused regression test first and confirm it fails for the
   intended reason; implement the smallest change, then rerun the focused and full unit suites.
3. Run the relevant integration level based on the changed component and risk. Record commands,
   mode/seed/configuration, result, and any blocker in the backlog or iteration log.
4. Review the diff and update user-facing setup, architecture, expected output, or this plan if the
   behavior or test procedure changed.
5. Mark backlog criteria complete only with evidence. Carry incomplete checks and discovered work
   forward; do not invent iteration history or claim unavailable checks passed.

## Risk-based regression map

| Change area | Minimum regression |
|---|---|
| Client protocol, retries, content handling | Unit suite + smoke + failover/checksum |
| Selector weights, health, or load | Unit suite + smoke + congestion scenario |
| Route state, ports, probes, flow moves | Unit suite + path failure/degradation/recovery |
| Topology, addresses, ports, or host counts | Compile check + six-client smoke + relevant full scenario |
| Experiment CSV/report code | Unit suite + quick experiment in both modes + report |
| Browser route visualizer | Unit regression + inspect live route page during a controller run |

## Definition of test-complete

A backlog item is test-complete when its acceptance criteria pass, relevant automated tests pass,
required integration checks have recorded results (or an explicit environment blocker), and the
iteration/backlog evidence is updated. A passing test suite alone does not establish performance
claims; performance results require reproducible runs and recorded configuration.

## Execution snapshot — November 12, 2026

| Check | Result |
|---|---|
| Unit/regression suite | 5 passed, 0 failed (`uv run python -m unittest discover -s tests -v`). |
| Static checks | Python compileall and `git diff --check` passed. |
| Standalone TCP delivery | 1,048,608 bytes delivered over loopback; SHA-256 verified; 0 retries. |
| Dynamic Mininet smoke | c1 and c2 each downloaded 2,097,152 bytes; checksums OK, 0 retries; expected s1 forward/reverse rules were installed. |
| Six-client smoke | c1–c6 all completed successfully; 0 retries each. |
| Server failover | 100 MiB transfer completed with checksum OK after 1 retry; server restarted afterward. |
| Path failure/recovery | Active transfer moved from s1 port 5 to backup port 12 without retries; subsequent transfer used direct port 5 after recovery; checksums OK. |
| Path degradation/recovery | Active transfer moved to backup port 12 without retries; subsequent transfer returned to direct port 5; checksums OK. |
| Report generation | `uv run python tests/run_scenarios.py report` succeeded and regenerated summary/figures from the existing 180-row `results/data/experiments.csv`. No new experiment measurements were collected, so those report values are not new results from this verification run. |
| Adaptive/random congestion and quick static/dynamic experiment matrix | NOT RUN. The adaptive scenario's sudo elevation timed out waiting for interactive authorization; the same privilege requirement blocks randomized congestion and Mininet experiment scenarios. |

The execution totals above count 14 checks as passed and 2 scenario groups as blocked/not run;
they do not imply that every planned acceptance case passed. The complete test-case matrix and
evidence are in `Smart_CDN_IEEE_829_Test_Plan.pdf`.

The PDF is also linked from the README.
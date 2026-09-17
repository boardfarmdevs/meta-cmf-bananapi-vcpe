# Release information

[Current state](current-state.md) is the single source for the deployed baseline,
latest distribution names, evidence locations and open limitations.

Each release records its exact runtime/source inputs and checksums. A source
build, a packaged candidate and an accepted fresh import are distinct states.
Dated acceptance records belong alongside immutable release artifacts, not in
a second growing chronology.

0916 is packaged as a **candidate with known issues**, at the owner's request
to stop debugging and complete distribution. Read `KNOWN-ISSUES-0916.md` and
the packaging receipt included with the artifacts. In particular, latest RDK
branch-room convergence/recovery failed despite valid rooted branches; the
complete current-source room catalog is not qualified. Archive checks and
VirtualBox boot checks do not substitute for room or fresh-import acceptance.

For older findings, use Git history, for example:
`git log --all -- doc/easymesh/current-state.md doc/easymesh/reference`.
Do not use an old acceptance report as the current operating manual.

# Runtime and data attribution

This implementation has no third-party Python package dependency and vendors no binaries or third-party source. It uses the user-installed Python 3.11 standard library and its bundled SQLite runtime.

- Python: [PSF license and incorporated-software notices](https://docs.python.org/3.11/license.html).
- SQLite deliverable library: [public-domain statement](https://www.sqlite.org/copyright.html).
- All business fixtures, metric definitions, synthetic user answers and decision faults are locally authored fictional material, covered by this repository's MIT license. The private-data canaries are synthetic test markers, not personal data.

Documentation references Databricks Genie and Vanna as prior art; neither is an imported dependency. No employer posting, external benchmark data or copied commercial query asset is included.

The unexecuted GitHub Actions configuration references pinned upstream actions/checkout and actions/setup-python under their MIT licenses; their source is not vendored. It selects CPython 3.11.9 on a standard Ubuntu runner, with no pip dependencies or application secrets. Exact immutable action metadata was read from the official repositories on 8 October 2026: [checkout](https://raw.githubusercontent.com/actions/checkout/11bd71901bbe5b1630ceea73d27597364c9af683/action.yml), [setup-python](https://raw.githubusercontent.com/actions/setup-python/a26af69be951a213d495a4c3e4e4022e16d87065/action.yml). Hosted execution remains unverified.

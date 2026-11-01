# datasets

This experiment uses synthetic banking data only: no real customer data, credentials or production systems. The data is generated in code (`mcp_vs_code_mode.banking.dataset`); no data files are committed.

## Generator

- **Version:** `1.1.0` (`DATASET_VERSION`). Version 1.1.0 appended volume 100; the data for volumes 10, 50 and 200 and the unauthorized customer is byte-identical to 1.0.0 (guarded by `test_existing_volumes_unchanged`) because volume 100 is generated last from the same random stream.
- **Seed:** `20261001` (`DEFAULT_SEED`); all randomness comes from one local `random.Random(seed)`.
- **Reference date:** 2026-10-01. **Analysis window:** 2026-07-03 to 2026-10-01 inclusive (90 days).
- **Volumes:** 10, 50, 100 and 200 transactions per account.
- **Customers and accounts:** one customer per volume (`CUST-0010`, `CUST-0050`, `CUST-0100`, `CUST-0200`), each with four accounts `ACC-<volume>-1..4` (current, savings, credit card, joint current).
- **Transaction IDs:** `TXN-<volume>-<account index>-<k>`, numbered in date order.
- **Categories:** groceries, dining, transport, utilities, shopping, entertainment, plus `income` for credits. Merchant names are generic.
- **Large debits:** each account has `max(1, volume // 25)` debits with an absolute amount above 1,000; all other debits are below 400.
- **Unauthorized customer:** `CUST-9999` with account `ACC-9999-1` and 5 transactions. The benchmark principal is not allowed to access it; it exists to test authorization.
- Amounts are rounded to 2 decimal places; a negative amount is a debit.

## Guarding against accidental change

A golden checksum test (`tests/unit/test_dataset.py`) pins the SHA-256 of the default dataset. Changing the generator invalidates comparability of benchmark results, so update the checksum deliberately and bump `DATASET_VERSION`. A second test pins fingerprints of the volumes present in 1.0.0 so that appending volumes cannot silently change them.
